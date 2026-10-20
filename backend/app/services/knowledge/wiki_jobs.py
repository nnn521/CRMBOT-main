"""Bounded wiki jobs using existing storage queues, leases and schema.

Call enqueue(), let a shared dispatcher use storage.claim_job(), then call
process_claimed(job) ONLY for KIND. claim_job has no kind filter, so this module
never steals other workers' jobs. The supplied budgeted client is never created
here. One bounded model call runs between sequential heartbeat operations; no
concurrent use of the repository's exclusively owned connection occurs.

Sources must belong to a fixed published release and be freshly resolvable.
The target MUST be a different, building release with identical dependency
span/version chunks already populated. Current schema does not allow writing or
reviewing wiki in a published release. This service neither copies chunks nor
builds/activates releases. An API must authenticate/authorize enqueue and human
review separately; a review call here does not authenticate a human.

Storage write methods each own transactions and forbid an outer transaction.
The small persistence transaction below therefore uses their parameterized SQL
shape directly: lock/fence job, fresh source checks, draft+claims+dependencies,
final fenced job completion. Any failure/expiry rolls the WHOLE transaction
back. No partial draft is left behind. The job row lock serializes reclaim;
clock_timestamp at the final write prevents a stalled owner committing late.

All persisted claims remain source-bound quotations, with original context and
freshness requirements. No quote is a timeless price/stock fact. Current prices
and stock require the separate deterministic business-tool path. Human approval
never removes these restrictions or proves semantic entailment.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import json
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, StringConstraints
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.services.knowledge.domain import Evidence, SourceLocator, document_fingerprint
from app.services.knowledge.evidence import (
    CitationValidator, EvidenceUnavailable, EvidenceValidationError, GenerationSchema,
    JsonModelClient, SpanId, StorageEvidenceRevalidator,
)
from app.services.knowledge.storage import EVIDENCE_SQL, KnowledgeStorage, LeaseLost
from app.services.knowledge.wiki import WikiCompilation, WikiCompilationError, WikiCompiler


KIND = "wiki_compile"
PROMPT_REVISION = "wiki-jobs-extractive-v1"


class WikiJobRequest(GenerationSchema):
    source_release_id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    target_release_id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    topic: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    span_ids: Annotated[list[SpanId], Field(min_length=1, max_length=24)]

    def check_request(self) -> None:
        if self.source_release_id == self.target_release_id:
            raise ValueError("published source and building target must differ")
        if any(not value.strip() or "\x00" in value for value in
               (self.source_release_id, self.target_release_id, self.topic)):
            raise ValueError("job fields must be nonempty text without NUL")
        if len(set(self.span_ids)) != len(self.span_ids):
            raise ValueError("span_ids must be unique")


@dataclass(frozen=True, slots=True)
class WikiJobOutcome:
    job_id: UUID
    status: Literal["succeeded", "failed", "lease_lost"]
    draft_id: str | None = None
    error_code: str | None = None


class WikiJobService:
    def __init__(self, storage: KnowledgeStorage, client: JsonModelClient, *,
                 compiler_model: str, lease_seconds: int = 60, model_timeout: float = 30):
        if not isinstance(compiler_model, str) or not compiler_model.strip() or len(compiler_model) > 200:
            raise ValueError("compiler_model must be bounded nonempty text")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 5 <= lease_seconds <= 86400:
            raise ValueError("lease_seconds must be an integer in [5, 86400]")
        if isinstance(model_timeout, bool) or not isinstance(model_timeout, (int, float)) or not 0 < model_timeout < lease_seconds:
            raise ValueError("model_timeout must be positive and shorter than the lease")
        self.storage = storage
        self.client = client
        self.compiler_model = compiler_model
        self.lease_seconds = lease_seconds
        self.model_timeout = model_timeout

    async def enqueue(self, idempotency_key: str, *, source_release_id: str,
                      target_release_id: str, topic: str, span_ids: Sequence[str],
                      max_attempts: int = 1) -> Mapping[str, Any]:
        """Queue IDs/topic only; never store API keys, clients or source bodies.

        Default one attempt avoids automatic repeated paid calls. Explicit retry
        budgets remain subject to the injected client's budget ledger.
        """
        request = WikiJobRequest.model_validate({
            "source_release_id": source_release_id, "target_release_id": target_release_id,
            "topic": topic, "span_ids": list(span_ids),
        })
        request.check_request()
        return await self.storage.enqueue_job(idempotency_key, KIND, request.model_dump(),
                                              max_attempts=max_attempts)

    async def _load(self, request: WikiJobRequest) -> tuple[Evidence, ...]:
        items = []
        for span_id in request.span_ids:
            # Public storage read enforces published, valid and non-revoked sources.
            row = await self.storage.get_citation(request.source_release_id, span_id)
            if row is None:
                raise EvidenceUnavailable("published source is unavailable")
            async with self.storage.connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    "SELECT doc_id FROM knowledge.source_document WHERE source_id = %s",
                    (row["source_id"],),
                )
                identity = await cursor.fetchone()
            if identity is None:
                raise EvidenceUnavailable("source identity is unavailable")
            item = Evidence(identity["doc_id"], row["version_id"], row["original_text"],
                            tuple(row["section_path"]), SourceLocator(**row["locator"]))
            if item.span_id != span_id:
                raise EvidenceValidationError("stored span cannot reconstruct original Evidence")
            items.append(item)
        return tuple(items)

    async def _check_target(self, request: WikiJobRequest, evidence: tuple[Evidence, ...]) -> None:
        # Fail before a paid call if the schema's build/dependency prerequisites
        # have not been prepared. DB triggers check again during persistence.
        async with self.storage.connection.cursor(row_factory=dict_row) as cursor:
            for item in evidence:
                await cursor.execute("""SELECT c.span_id FROM knowledge.retrieval_chunk c
                    JOIN knowledge.knowledge_release r ON r.release_id = c.release_id
                    WHERE c.release_id = %s AND r.status = 'building'
                      AND c.span_id = %s AND c.version_id = %s LIMIT 1""",
                    (request.target_release_id, item.span_id, item.doc_version))
                if await cursor.fetchone() is None:
                    raise EvidenceUnavailable("building target lacks an original dependency chunk")

    async def process_claimed(self, job: Mapping[str, Any]) -> WikiJobOutcome:
        """Process dispatcher-owned wiki job; return only sanitized failure codes.

        Unknown kinds are rejected without finishing a different service's job.
        job_id and lease_token must be UUIDs from trusted storage.claim_job().
        """
        if job.get("kind") != KIND:
            raise ValueError("dispatcher must route only wiki_compile jobs")
        job_id, token = job.get("job_id"), job.get("lease_token")
        if not isinstance(job_id, UUID) or not isinstance(token, UUID):
            raise ValueError("trusted claimed job UUID and fencing token are required")
        try:
            request = WikiJobRequest.model_validate(job.get("payload"))
            request.check_request()
            await self.storage.heartbeat_job(job_id, token, lease_seconds=self.lease_seconds)
            evidence = await self._load(request)
            await self._check_target(request, evidence)
            checker = StorageEvidenceRevalidator(self.storage, request.source_release_id)
            async with asyncio.timeout(self.model_timeout):
                compiled = await WikiCompiler(self.client, revalidate=checker).compile(request.topic, evidence)
            # Renew before entering persistence. This fails before any write if
            # the model outlived its lease or a different worker reclaimed it.
            await self.storage.heartbeat_job(job_id, token, lease_seconds=self.lease_seconds)
            await CitationValidator(evidence, revalidate=checker).recheck(
                [dep.span_id for dep in compiled.dependencies])
            draft_id = await self._persist(job_id, token, request, evidence, compiled)
            return WikiJobOutcome(job_id, "succeeded", draft_id=draft_id)
        except LeaseLost:
            return WikiJobOutcome(job_id, "lease_lost", error_code="lease_lost")
        except Exception as exc:
            # Never str(exc), provider body, request payload, key, or traceback.
            if isinstance(exc, EvidenceUnavailable):
                code = "wiki_source_unavailable"
            elif isinstance(exc, (EvidenceValidationError, ValueError)):
                code = "wiki_invalid_evidence_or_output"
            elif isinstance(exc, (WikiCompilationError, TimeoutError)):
                code = "wiki_model_failed"
            else:
                code = "wiki_persistence_failed"
            try:
                await self.storage.finish_job(job_id, token, error=code)
            except LeaseLost:
                return WikiJobOutcome(job_id, "lease_lost", error_code="lease_lost")
            except Exception:
                return WikiJobOutcome(job_id, "failed", error_code="wiki_job_update_failed")
            return WikiJobOutcome(job_id, "failed", error_code=code)

    async def _persist(self, job_id: UUID, token: UUID, request: WikiJobRequest,
                       evidence: tuple[Evidence, ...], compiled: WikiCompilation) -> str:
        inventory = {item.span_id: item for item in evidence}
        draft_id = "wiki-job-" + str(job_id)
        claims = []
        for section_no, section in enumerate(compiled.draft.sections):
            for claim_no, claim in enumerate(section.claims):
                original = inventory[claim.span_id]
                # Persistent first version keeps whole spans, including conditions.
                if claim.quote != original.content:
                    raise EvidenceValidationError("persistent wiki requires complete source context")
                claims.append((section_no, claim_no, claim, original))
        body = json.dumps({
            "status": "draft", "review_required": True,
            "validation_scope": "quote_presence_only", "source_bound": True,
            "notice": "原文摘录须人工审核；不证明语义支持。价格与库存须查询实时业务工具，不得作为恒久事实。",
            "source_release_id": request.source_release_id,
            "sections": [{"heading": section.heading, "claims": [
                {"quote": claim.quote, "span_id": claim.span_id, "source_context": claim.source_context}
                for claim in section.claims]} for section in compiled.draft.sections],
        }, ensure_ascii=False, separators=(",", ":"))
        connection = self.storage.connection
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute("""SELECT job_id FROM knowledge.ingestion_job
                    WHERE job_id = %s AND lease_token = %s AND kind = %s
                      AND status = 'running' AND lease_until > clock_timestamp()
                    FOR UPDATE""", (job_id, token, KIND))
                if await cursor.fetchone() is None:
                    raise LeaseLost("wiki job lease expired or was replaced")
                # One fresh snapshot per selected span, same original provenance.
                for dep in compiled.dependencies:
                    item = inventory[dep.span_id]
                    await cursor.execute(EVIDENCE_SQL + " AND s.span_id = %s ORDER BY c.chunk_id LIMIT 1",
                                         (request.source_release_id, dep.span_id))
                    fresh = await cursor.fetchone()
                    if fresh is None or (fresh["version_id"], fresh["original_text"], fresh["locator"]) != (
                            item.doc_version, item.content, asdict(item.locator)):
                        raise EvidenceUnavailable("wiki dependency is no longer available")
                # Existing DB triggers enforce building target + unreviewed draft
                # and that each dependency belongs to a target retrieval chunk.
                await cursor.execute("""INSERT INTO knowledge.wiki_draft
                    (release_id,draft_id,title,body,compiler_model,prompt_revision)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (request.target_release_id, draft_id, compiled.draft.title, body,
                     self.compiler_model, PROMPT_REVISION))
                for section_no, claim_no, claim, original in claims:
                    claim_id = document_fingerprint(f"{draft_id}/{section_no}/{claim_no}")
                    conditions = {"source_bound": True, "timeless": False,
                                  "requires_fresh_source": True, "validation_scope": "quote_presence_only",
                                  "source_release_id": request.source_release_id,
                                  "live_price_or_inventory": "use_business_tool",
                                  "source_context": original.content}
                    await cursor.execute("""INSERT INTO knowledge.wiki_claim
                        (release_id,claim_id,draft_id,claim_text,conditions) VALUES (%s,%s,%s,%s,%s)""",
                        (request.target_release_id, claim_id, draft_id, claim.quote, Jsonb(conditions)))
                    await cursor.execute("""INSERT INTO knowledge.claim_dependency
                        (release_id,claim_id,span_id,version_id) VALUES (%s,%s,%s,%s)""",
                        (request.target_release_id, claim_id, original.span_id, original.doc_version))
                await cursor.execute("""UPDATE knowledge.ingestion_job SET status = 'succeeded',
                    lease_owner = NULL, lease_token = NULL, lease_until = NULL,
                    finished_at = clock_timestamp(), last_error = NULL
                    WHERE job_id = %s AND lease_token = %s AND kind = %s
                      AND status = 'running' AND lease_until > clock_timestamp() RETURNING job_id""",
                    (job_id, token, KIND))
                if await cursor.fetchone() is None:
                    raise LeaseLost("wiki job expired before persistence completed")
        return draft_id

    async def review(self, release_id: str, draft_id: str, *, approved: bool) -> None:
        """Explicit human decision path; caller enforces reviewer authentication.

        Review alone does not activate/publish a release. Storage enforces the
        building-only, one-way decision transition. No automated code calls this.
        """
        await self.storage.review_wiki_draft(release_id, draft_id, approved=approved)
