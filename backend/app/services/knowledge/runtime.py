"""Request-owned RAG v2 runtime. No connections, migrations or model calls at import.

Use ``async with open_knowledge_runtime() as runtime`` after authenticating the
caller. ``search`` pins one release, uses PostgreSQL dense search + fresh BM25,
and revalidates originals before returning. ``answer`` additionally uses the
budgeted extractive answer service, only with explicitly configured credentials.
Builds are durable jobs; run scripts/knowledge_worker.py separately. A successful
build is READY only: publication always requires an explicit administrator call.
"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app.core.config import Settings, settings
from app.services.knowledge.budget import BudgetLedger, TokenRates
from app.services.knowledge.domain import Evidence, SourceLocator, document_fingerprint
from app.services.knowledge.evidence import GroundedAnswer, GroundedAnswerService, StorageEvidenceRevalidator
from app.services.knowledge.model_client import DeepSeekClient, OllamaEmbeddingClient
from app.services.knowledge.parsing import parse_markdown
from app.services.knowledge.query import QueryEntity, QueryPlan, plan_query
from app.services.knowledge.ranking import BM25Index, ChineseTokenizer, reciprocal_rank_fusion
from app.services.knowledge.retrieval import Reranker, RetrievalResult, rerank_candidates
from app.services.knowledge.reranking import TEIReranker, should_rerank
from app.services.knowledge.storage import KnowledgeStorage, LeaseLost, ReleaseManifest, StorageConflict, corpus_checksum
from app.services.knowledge.synthesis import SynthesisAnswerService


class KnowledgeUnavailable(RuntimeError):
    """Public-safe failure; callers must not emit underlying exception messages."""


class KnowledgeNotFound(LookupError):
    pass


class QueryClarification(ValueError):
    """A rule-only clarification; contains public text, never provider details."""


def _power_parts(value: str | None) -> frozenset[str]:
    allowed = {"2.0", "2.5", "双擎", "燃油", "插混", "2.0 燃油", "2.0 双擎", "2.0 插混",
               "2.5 燃油", "2.5 双擎", "2.5 插混"}
    if value is not None and value not in allowed:
        raise ValueError("powertrain must be one of the canonical values")
    return frozenset(value.split()) if isinstance(value, str) else frozenset()


def _validated_metadata(metadata: dict | None) -> dict:
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object")
    value = {} if metadata is None else json.loads(_json_bytes(metadata))
    scopes = value.get("vehicle_scopes", [])
    if not isinstance(scopes, list) or len(scopes) > 50:
        raise ValueError("vehicle_scopes must be a bounded array")
    for scope in scopes:
        if not isinstance(scope, dict) or set(scope) - {"model", "year", "powertrain"}:
            raise ValueError("vehicle scope accepts model/year/powertrain only")
        if scope.get("model") not in {"CAMRY", "HIGHLANDER", "RAV4"}:
            raise ValueError("vehicle scope model must be canonical")
        year = scope.get("year")
        if year is not None and (type(year) is not int or not 2000 <= year <= 2099):
            raise ValueError("scope year must be a four-digit integer or null")
        power = scope.get("powertrain")
        if power is not None and not isinstance(power, str):
            raise ValueError("scope powertrain must be canonical text or null")
        _power_parts(power)
    return value


def _matches_scope(metadata: Any, entities: tuple[QueryEntity, ...]) -> bool:
    if not entities:
        return True
    try:
        metadata = _validated_metadata(metadata)
    except (ValueError, TypeError):
        return False
    # OR across complete model/year/powertrain tuples, never across individual
    # attributes. Unknown source fields cannot satisfy an explicit constraint.
    return any(scope["model"] == entity.model
               and (entity.year is None or scope.get("year") == entity.year)
               and (entity.powertrain is None or
                    _power_parts(entity.powertrain) <= _power_parts(scope.get("powertrain")))
               for scope in metadata.get("vehicle_scopes", []) for entity in entities)


def _public_limitation(reason: str | None) -> str:
    """Bundle copy only; retrieval/API diagnostic codes remain unchanged."""
    return {
        "embedding_unavailable": "向量检索暂不可用，本次使用关键词检索。",
        "reranker_unavailable": "相关性重排暂不可用，本次保留原检索顺序。",
        "model_not_configured": "知识问答服务尚未配置完成。",
        "empty_evidence": "当前没有符合问题范围的可用来源原文。",
        "evidence_unavailable": "引用来源已失效或暂时无法核对。",
        "evidence_budget_exceeded": "来源内容较长，请缩小问题范围后重试。",
        "model_failure": "知识问答服务暂不可用。",
        "invalid_output": "未能从来源中选出可核对的完整原文。",
        "no_selected_evidence": "现有来源不足以回答该问题。",
        "knowledge_unavailable": "知识检索或引用核对暂不可用。",
    }.get(reason, "当前没有可输出的来源原文。")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _artifact(chunks: list[dict]) -> bytes:
    tokenizer = ChineseTokenizer()
    return _json_bytes({"schema": "bm25-zh-bigram-v1", "documents": [
        {"chunk_id": c["chunk_id"], "span_id": c["span_id"], "tokens": list(tokenizer(c["content"]))}
        for c in sorted(chunks, key=lambda c: c["chunk_id"])
    ]})


def _original_evidence(text: str, *, doc_id: str, source_id: str, version_id: str) -> tuple[Evidence, ...]:
    """Preserve exact original lines, including table headers and conditions.

    Parser content is useful for discovery but can repeat headings or rewrite
    table cells. Citations instead use literal source ranges; locator.source is
    the public logical ID, never an on-disk path or administrator-supplied URI.
    """
    lines = text.splitlines(keepends=True)
    result = []
    for parsed in parse_markdown(text, doc_id=doc_id, source=source_id):
        loc = parsed.locator
        starts = [loc.start_line] + [n for n in (loc.header_start_line, loc.context_start_line) if n is not None]
        loc = SourceLocator(source_id, min(starts), loc.end_line, loc.kind,
                            loc.header_start_line, loc.header_end_line,
                            loc.context_start_line, loc.context_end_line)
        original = "".join(lines[loc.start_line - 1:loc.end_line])
        if len(original) > 16000:
            raise ValueError("source span exceeds 16000 characters; split long paragraphs")
        result.append(Evidence(doc_id, version_id, original, parsed.section_path, loc))
    if not result:
        raise ValueError("Markdown contains no source evidence")
    return tuple(result)


class RevisionEmbeddingClient:
    """Fail closed unless the served Ollama model digest matches the manifest."""

    def __init__(self, config: Settings):
        self.config = config
        self.client = OllamaEmbeddingClient(base_url=config.knowledge_ollama_base_url,
            model=config.knowledge_embedding_model, dimension=config.knowledge_embedding_dimension,
            timeout=config.knowledge_http_timeout_seconds)

    async def _check_revision(self) -> None:
        config = self.config
        if not config.knowledge_embedding_revision.startswith("sha256:") or len(config.knowledge_embedding_revision) != 71:
            raise KnowledgeUnavailable("embedding revision is not configured")
        async with httpx.AsyncClient(timeout=config.knowledge_http_timeout_seconds) as client:
            response = await client.get(config.knowledge_ollama_base_url.rstrip("/") + "/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
        name = config.knowledge_embedding_model
        names = {name, name + ":latest"} if ":" not in name else {name}
        matching = [m for m in models if m.get("name") in names or m.get("model") in names]
        # Ollama's /api/tags reports a bare 64-hex digest; configuration keeps the
        # explicit sha256: form so it cannot be confused with another hash scheme.
        expected = config.knowledge_embedding_revision.removeprefix("sha256:")
        if len(matching) != 1 or matching[0].get("digest") != expected:
            raise KnowledgeUnavailable("embedding revision unavailable")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            async with asyncio.timeout(self.config.knowledge_http_timeout_seconds):
                await self._check_revision()
                result = await self.client.embed(texts)
                await self._check_revision()
                return result
        except Exception as exc:
            raise KnowledgeUnavailable("embedding service unavailable") from exc


class KnowledgeRuntime:
    def __init__(self, storage: KnowledgeStorage, config: Settings, *, embedder=None,
                 reranker: Reranker | None = None):
        self.storage = storage
        self.config = config
        self.embedder = embedder if embedder is not None else RevisionEmbeddingClient(config)
        self._doc_ids: dict[str, str] = {}  # immutable identities, request-local only
        self.reranker = reranker

    def _match_manifest(self, row: dict) -> ReleaseManifest:
        manifest = ReleaseManifest.from_row(row)
        config = self.config
        if (manifest.embedding_model, manifest.embedding_revision, manifest.embedding_dim,
            manifest.embedding_normalized, manifest.distance_metric) != (
            config.knowledge_embedding_model, config.knowledge_embedding_revision,
            config.knowledge_embedding_dimension, True, "cosine"):
            raise KnowledgeUnavailable("query embedding configuration differs from published release")
        return manifest

    async def status(self) -> dict:
        row = await self.storage.pin_active_release()
        compatible = False
        if row:
            try:
                self._match_manifest(row)
                compatible = True
            except (ValueError, KnowledgeUnavailable):
                pass
        return {"enabled": True, "ready": bool(row) and compatible,
                "release_id": row["release_id"] if row else None,
                "embedding_compatible": compatible, "scope": "shared_authenticated"}

    async def _evidence(self, row: dict) -> Evidence:
        source_id = row["source_id"]
        if source_id not in self._doc_ids:
            source = await self.storage._one(
                "SELECT doc_id FROM knowledge.source_document WHERE source_id = %s", (source_id,))
            if not source:
                raise KnowledgeUnavailable("evidence source unavailable")
            self._doc_ids[source_id] = source["doc_id"]
        evidence = Evidence(self._doc_ids[source_id], row["version_id"], row["original_text"],
                            tuple(row["section_path"]), SourceLocator(**row["locator"]))
        if evidence.span_id != row["span_id"] or evidence.locator.source != row["source_id"]:
            raise KnowledgeUnavailable("evidence identity mismatch")
        return evidence

    async def citation(self, release_id: str, span_id: str) -> dict:
        row = await self.storage.get_citation(release_id, span_id)
        if row is None:
            raise KnowledgeNotFound("citation unavailable")
        evidence = await self._evidence(row)
        if not await StorageEvidenceRevalidator(self.storage, release_id)(evidence):
            raise KnowledgeNotFound("citation unavailable")
        return {"release_id": release_id, "span_id": evidence.span_id,
                "doc_id": evidence.doc_id, "version_id": evidence.doc_version,
                "source_id": row["source_id"], "title": row["title"],
                "original_text": evidence.content, "locator": asdict(evidence.locator),
                "section_path": list(evidence.section_path)}

    async def search(self, query: str, *, top_k: int = 5,
                     query_plan: QueryPlan | None = None) -> RetrievalResult:
        if not isinstance(query, str) or not query.strip() or len(query) > 2000 or not 1 <= top_k <= 20:
            raise ValueError("query/top_k outside supported bounds")
        if query_plan is not None and not isinstance(query_plan, QueryPlan):
            raise TypeError("query_plan must be a server-owned QueryPlan")
        plan = query_plan if query_plan is not None else plan_query(query)
        if plan.clarification:
            raise QueryClarification(plan.clarification)
        planned = plan.query
        # Appended canonical scope is bounded independently of raw query length.
        if len(planned) > 4000:
            raise ValueError("planned query exceeds supported bounds")
        release = await self.storage.pin_active_release()
        if release is None:
            raise KnowledgeUnavailable("no published knowledge release")
        manifest = self._match_manifest(release)
        release_id = release["release_id"]
        # No vector columns are loaded in Python. Fresh eligibility also scopes
        # BM25 statistics, not only its final top-k, after revocation/expiry.
        rows = await self.storage.list_evidence(release_id)
        artifact = release.get("evaluation", {}).get("bm25_artifact")
        if not isinstance(artifact, str) or hashlib.sha256(artifact.encode("utf-8")).hexdigest() != manifest.bm25_sha256:
            raise KnowledgeUnavailable("BM25 artifact missing or corrupt")
        artifact_data = json.loads(artifact)
        if artifact_data.get("schema") != "bm25-zh-bigram-v1":
            raise KnowledgeUnavailable("BM25 artifact schema mismatch")
        indexed = {c["chunk_id"]: c for c in artifact_data["documents"]}
        tokenizer = ChineseTokenizer()
        if any(indexed.get(r["chunk_id"]) != {"chunk_id": r["chunk_id"], "span_id": r["span_id"],
               "tokens": list(tokenizer(r["content"]))} for r in rows):
            raise KnowledgeUnavailable("BM25 artifact differs from stored chunks")
        source_inventory: dict[str, set[str]] = {}
        for row in rows:
            source_inventory.setdefault(row["source_id"], set()).add(row["version_id"])
        if any(len(versions) != 1 for versions in source_inventory.values()):
            raise KnowledgeUnavailable("release contains multiple versions per source")
        rows = [row for row in rows if _matches_scope(row.get("metadata"), plan.entities)]
        if not rows:
            return RetrievalResult(release_id, (), ())
        # Dense narrows by source_id before top-k. Guard the one-version/source
        # invariant even for releases created outside this runtime, otherwise a
        # second version could silently broaden the SQL candidate scope.
        source_versions = {}
        for row in rows:
            previous = source_versions.setdefault(row["source_id"], row["version_id"])
            if previous != row["version_id"]:
                raise KnowledgeUnavailable("release contains multiple scoped versions per source")
        source_ids = sorted(source_versions)
        evidence = tuple([await self._evidence(row) for row in rows])
        by_id = {e.span_id: e for e in evidence}
        async def semantic():
            try:
                async with asyncio.timeout(self.config.knowledge_http_timeout_seconds):
                    vectors = await self.embedder.embed([planned])
                if len(vectors) != 1:
                    raise ValueError("query embedding count mismatch")
                return vectors[0]
            except Exception:
                return None
        sparse, query_vector = await asyncio.gather(
            asyncio.to_thread(lambda: BM25Index(evidence).search(planned, top_k=20)), semantic())
        degraded = ()
        dense = ()
        if query_vector is None:
            degraded = ("embedding_unavailable",)
        else:
            # SQL/manifest failures remain fatal; only unavailable network
            # embedding degrades explicitly to independently valid BM25 evidence.
            dense_rows = await self.storage.search_dense(release_id, query_vector,
                embedding_model=manifest.embedding_model, embedding_revision=manifest.embedding_revision,
                limit=20, source_ids=source_ids)
            dense = tuple(by_id[r["span_id"]] for r in dense_rows if r["span_id"] in by_id)
        candidates = reciprocal_rank_fusion((sparse, dense), top_k=20)
        validator = StorageEvidenceRevalidator(self.storage, release_id)
        safe = []
        for item in candidates:
            if await validator(item.evidence):
                safe.append(item)
        candidates = tuple(safe)
        ranked = candidates
        config = self.config
        if config.knowledge_rerank_enabled and should_rerank(planned, candidates, top_k=top_k,
                min_candidates=config.knowledge_rerank_min_candidates,
                max_relative_gap=config.knowledge_rerank_max_relative_gap):
            try:
                reranker = self.reranker or TEIReranker(base_url=config.knowledge_rerank_base_url,
                    model=config.knowledge_rerank_model, timeout=config.knowledge_rerank_timeout_seconds)
                ranked = await rerank_candidates(planned, candidates, reranker=reranker,
                                                  timeout=config.knowledge_rerank_timeout_seconds)
            except Exception:
                degraded += ("reranker_unavailable",)
            # A source may be withdrawn while the HTTP scorer runs. Never emit
            # pre-rerank eligibility alone, even when inference failed/timed out.
            allowed = set()
            for item in candidates:
                if await validator(item.evidence):
                    allowed.add(item.evidence.span_id)
            candidates = tuple(item for item in candidates if item.evidence.span_id in allowed)
            ranked = tuple(item for item in ranked if item.evidence.span_id in allowed)
        return RetrievalResult(release_id, candidates, ranked[:top_k], degraded)

    def _answer_configured(self) -> bool:
        config = self.config
        return bool(config.knowledge_api_key and config.knowledge_budget_cny and
                    config.knowledge_input_per_million_cny and config.knowledge_output_per_million_cny)

    async def answer(self, query: str, *, top_k: int = 5,
                     previous_user_messages: Sequence[str] = (),
                     query_plan: QueryPlan | None = None) -> GroundedAnswer:
        if not self._answer_configured():
            return GroundedAnswer("unavailable", "知识问答模型未配置。", reason="model_failure")
        plan = query_plan if query_plan is not None else plan_query(query, previous_user_messages)
        result = await self.search(query, top_k=top_k, query_plan=plan)
        return await self._answer_result(plan.query, result)

    async def _answer_result(self, query: str, result: RetrievalResult) -> GroundedAnswer:
        config = self.config
        budget_path = Path(config.knowledge_budget_path)
        if not budget_path.is_absolute():
            budget_path = Path(__file__).resolve().parents[3] / budget_path
        ledger = await asyncio.to_thread(BudgetLedger, budget_path, Decimal(str(config.knowledge_budget_cny)))
        client = DeepSeekClient(api_key=config.knowledge_api_key, model=config.knowledge_answer_model,
            rates=TokenRates(Decimal(str(config.knowledge_input_per_million_cny)),
                             Decimal(str(config.knowledge_output_per_million_cny))),
            ledger=ledger, timeout=config.knowledge_http_timeout_seconds, base_url=config.knowledge_api_base_url)
        revalidate = StorageEvidenceRevalidator(self.storage, result.release_id)
        evidence = tuple(item.evidence for item in result.ranked)
        if config.knowledge_answer_mode == "synthesized":
            # Single structured call; every claim stays tied to a complete original
            # span. Structural citation checks are not a semantic-support proof.
            service = SynthesisAnswerService(client, revalidate=revalidate)
            return await service.answer(query, evidence)
        return await GroundedAnswerService(client, revalidate=revalidate).answer(query, evidence)

    async def answer_bundle(self, query: str, *, top_k: int = 5,
                            previous_user_messages: Sequence[str] = ()) -> dict:
        """Graph adapter: one plan/search/generation with pinned live citations.

        ``previous_user_messages`` must be user-only text from the server
        checkpoint. The raw query is planned exactly once here; the resulting
        server-owned QueryPlan is passed internally to search (never HTTP input).
        A rule clarification skips storage, embedding and model calls. This is
        source_quotes_only, not a semantic-synthesis accuracy claim.
        """
        if self.config.knowledge_answer_mode == "synthesized":
            mode_note = ["回答依据来源整理，敏感事项保留完整原文和适用条件。",
                         "引用已核对与来源原文一致，尚未经过人工语义评审。"]
        else:
            mode_note = ["原文摘录模式。", "仅核对引用与来源原文是否一致，回答适用性仍需结合版本条件。"]
        bundle = {"reply": "当前没有可输出的已核验证据。", "citations": [],
                  "knowledge_results": [], "knowledge_release_id": None,
                  "answer_status": "unavailable", "data_as_of": None,
                  "assumptions": [], "limitations": mode_note}
        plan = plan_query(query, previous_user_messages)
        if plan.clarification:
            bundle.update(reply=plan.clarification, answer_status="clarification",
                          limitations=["需要先明确车型、年款或动力版本。"])
            return bundle
        if not self._answer_configured():
            bundle["limitations"].append(_public_limitation("model_not_configured"))
            return bundle
        try:
            result = await self.search(query, top_k=top_k, query_plan=plan)
            bundle["knowledge_release_id"] = result.release_id
            bundle["limitations"].extend(_public_limitation(reason) for reason in result.degraded)
            answer = await self._answer_result(plan.query, result)
            if answer.status != "ok":
                bundle["limitations"].append(_public_limitation(answer.reason))
                return bundle
            citations = []
            for quote in answer.quotes:
                row = await self.citation(result.release_id, quote.span_id)
                citations.append({"citation_id": quote.citation_id, "span_id": quote.span_id,
                    "source_id": row["source_id"], "document_version": row["version_id"],
                    "title": row["title"], "locator": row["locator"], "quote": quote.quote,
                    "url": f"{self.config.api_v1_prefix}/knowledge/releases/{result.release_id}/citations/{quote.span_id}"})
            scores = {item.evidence.span_id: item.score for item in result.ranked}
            bundle.update(reply=answer.summary + "\n\n" + "\n\n".join(answer.claims),
                citations=citations, answer_status="partial" if result.degraded else "answered",
                knowledge_results=[{"content": c["quote"], "score": scores[c["span_id"]],
                                    "source": c["source_id"], "span_id": c["span_id"]} for c in citations])
            return bundle
        except QueryClarification as exc:
            bundle.update(reply=str(exc), answer_status="clarification",
                          limitations=["需要先明确车型、年款或动力版本。"])
            return bundle
        except Exception:
            bundle["limitations"].append(_public_limitation("knowledge_unavailable"))
            return bundle

    async def create_source(self, *, doc_id: str, source_uri: str) -> dict:
        source_id = "src-" + uuid4().hex
        await self.storage.create_source(source_id, doc_id, source_uri)
        return {"source_id": source_id, "doc_id": doc_id}

    async def list_sources(self) -> list[dict]:
        return await self.storage._rows("""
            SELECT s.source_id,s.doc_id,s.source_uri,s.created_at,
                   (r.source_id IS NOT NULL) AS revoked
            FROM knowledge.source_document s LEFT JOIN knowledge.source_revocation r USING(source_id)
            ORDER BY s.created_at DESC LIMIT 200
            """)

    async def upload(self, source_id: str, content: bytes, *, title: str,
                     metadata: dict | None = None) -> dict:
        if not content or len(content) > self.config.knowledge_upload_max_bytes:
            raise ValueError("upload exceeds byte limit or is empty")
        metadata = _validated_metadata(metadata)
        try:
            text = content.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError("only UTF-8 text is accepted") from exc
        if any(ord(c) < 32 and c not in "\n\r\t" for c in text) or not text.strip():
            raise ValueError("upload must contain plain UTF-8 text")
        source = await self.storage._one("""
            SELECT doc_id FROM knowledge.source_document s WHERE source_id = %s
            AND NOT EXISTS (SELECT 1 FROM knowledge.source_revocation r WHERE r.source_id=s.source_id)
            """, (source_id,))
        if source is None:
            raise KnowledgeNotFound("source unavailable")
        # Preserve Evidence.doc_version == original SHA-256. The current schema
        # has a global version PK: reject cross-source collisions explicitly
        # rather than merging provenance or breaking citation revalidation.
        version_id = document_fingerprint(content)
        existing = await self.storage._one("SELECT source_id FROM knowledge.document_version WHERE version_id=%s", (version_id,))
        if existing is not None:
            raise StorageConflict("these original bytes already have a registered version")
        spans = _original_evidence(text, doc_id=source["doc_id"], source_id=source_id, version_id=version_id)
        if len(spans) > self.config.knowledge_max_build_chunks:
            raise ValueError("document exceeds chunk limit")
        await self.storage.add_version(version_id, source_id, content, title, metadata=metadata)
        return {"source_id": source_id, "version_id": version_id, "span_count": len(spans)}

    async def enqueue_build(self, version_ids: list[str], *, idempotency_key: str, requested_by: str) -> dict:
        versions = sorted(set(version_ids))
        if not versions or len(versions) != len(version_ids) or len(versions) > 100:
            raise ValueError("build requires 1-100 distinct versions")
        rows = await self._build_versions(versions)
        if len(rows) != len(versions) or len({r["source_id"] for r in rows}) != len(rows):
            raise ValueError("choose one existing non-revoked version per source")
        self._parse_versions(rows)  # Reject unbuildable corpora before queueing.
        job = await self.storage.enqueue_job("markdown:" + idempotency_key, "markdown_build",
            {"version_ids": versions, "requested_by": requested_by}, max_attempts=3)
        return self._job_public(job)

    @staticmethod
    def _job_public(job: dict) -> dict:
        return {"job_id": str(job["job_id"]), "status": job["status"], "attempts": job["attempts"],
                "error": "build_failed" if job.get("last_error") else None,
                "release_id": f"rel-{job['job_id']}-{job['attempts']}" if job["attempts"] else None}

    async def build_status(self, job_id: UUID) -> dict:
        job = await self.storage._one("SELECT * FROM knowledge.ingestion_job WHERE job_id=%s AND kind='markdown_build'", (job_id,))
        if job is None:
            raise KnowledgeNotFound("build unavailable")
        result = self._job_public(job)
        release = await self.storage._one("SELECT status FROM knowledge.knowledge_release WHERE release_id=%s", (result["release_id"],))
        result["release_status"] = release["status"] if release else None
        return result

    async def _build_versions(self, version_ids: list[str]) -> list[dict]:
        return await self.storage._rows("""
            SELECT d.version_id,d.source_id,d.original_content,s.doc_id
            FROM knowledge.document_version d JOIN knowledge.source_document s USING(source_id)
            WHERE d.version_id=ANY(%s::text[])
            AND d.valid_from <= statement_timestamp() AND statement_timestamp() < d.valid_until
            AND NOT EXISTS (SELECT 1 FROM knowledge.source_revocation r WHERE r.source_id=d.source_id)
            ORDER BY d.version_id
            """, (version_ids,))

    def _parse_versions(self, rows: list[dict]) -> tuple[Evidence, ...]:
        spans = []
        for row in rows:
            spans.extend(_original_evidence(bytes(row["original_content"]).decode("utf-8"),
                doc_id=row["doc_id"], source_id=row["source_id"], version_id=row["version_id"]))
        if not spans or len(spans) > self.config.knowledge_max_build_chunks:
            raise ValueError("build exceeds chunk limit or contains no evidence")
        return tuple(spans)

    async def run_one_job(self, worker: str) -> bool:
        """Claim with fencing; heartbeats use this exclusively owned connection.

        Failed/recovered attempts get a new release, so partial immutable chunks
        never collide with a retry. Only finish_job's current lease can make a
        READY release publishable through the API.
        """
        lease_seconds = max(60, int(self.config.knowledge_http_timeout_seconds) + 30)
        job = await self.storage.claim_job(worker, lease_seconds=lease_seconds)
        if job is None:
            return False
        job_id, token = job["job_id"], job["lease_token"]
        release_id = f"rel-{job_id}-{job['attempts']}"
        created = False
        try:
            if job["kind"] != "markdown_build":
                raise ValueError("unsupported build kind")
            versions = job["payload"]["version_ids"]
            rows = await self._build_versions(versions)
            if len(rows) != len(versions):
                raise ValueError("build source unavailable")
            spans = self._parse_versions(rows)
            chunks = [{"chunk_id": e.span_id, "span_id": e.span_id, "version_id": e.doc_version,
                       "content": e.content, "token_count": max(1, len(ChineseTokenizer()(e.content)))} for e in spans]
            artifact = _artifact(chunks)
            config = self.config
            manifest = ReleaseManifest(config.knowledge_embedding_model, config.knowledge_embedding_revision,
                config.knowledge_embedding_dimension, True, len(chunks), corpus_checksum(chunks),
                hashlib.sha256(artifact).hexdigest())
            await self.storage.create_release(release_id, manifest,
                evaluation={"compiler": "markdown-original-v1", "job_id": str(job_id),
                            "bm25_artifact": artifact.decode("utf-8")})
            created = True
            for offset in range(0, len(spans), 32):
                await self.storage.heartbeat_job(job_id, token, lease_seconds=lease_seconds)
                batch = spans[offset:offset + 32]
                async with asyncio.timeout(config.knowledge_http_timeout_seconds):
                    vectors = await self.embedder.embed([e.content for e in batch])
                if len(vectors) != len(batch):
                    raise ValueError("embedding row count mismatch")
                await self.storage.heartbeat_job(job_id, token, lease_seconds=lease_seconds)
                for evidence, vector, chunk in zip(batch, vectors, chunks[offset:offset + 32]):
                    # Evidence is deterministic across attempts; verify any reused row.
                    existing = await self.storage._one("SELECT version_id,original_text,locator,section_path FROM knowledge.evidence_span WHERE span_id=%s", (evidence.span_id,))
                    expected = {"version_id": evidence.doc_version, "original_text": evidence.content,
                                "locator": asdict(evidence.locator), "section_path": list(evidence.section_path)}
                    if existing is None:
                        # Separate workers may share spans; ON CONFLICT preserves
                        # immutable originals, followed by an exact comparison.
                        await self.storage.connection.execute("""
                            INSERT INTO knowledge.evidence_span(span_id,version_id,original_text,locator,section_path)
                            VALUES (%s,%s,%s,%s,%s) ON CONFLICT (span_id) DO NOTHING
                            """, (evidence.span_id, evidence.doc_version, evidence.content,
                                   Jsonb(expected["locator"]), Jsonb(expected["section_path"])))
                        existing = await self.storage._one("SELECT version_id,original_text,locator,section_path FROM knowledge.evidence_span WHERE span_id=%s", (evidence.span_id,))
                    if existing != expected:
                        raise StorageConflict("source span identity conflict")
                    await self.storage.add_chunk(release_id, chunk["chunk_id"], evidence.span_id,
                        evidence.doc_version, evidence.content, chunk["token_count"], vector)
                    await self.storage.heartbeat_job(job_id, token, lease_seconds=lease_seconds)
            await self.storage.mark_ready(release_id, artifact)
            await self.storage.finish_job(job_id, token)
        except LeaseLost:
            return True
        except Exception:
            if created:
                try:
                    await self.storage.fail_release(release_id)
                except Exception:
                    pass
            try:
                await self.storage.finish_job(job_id, token, error="knowledge_build_failed")
            except LeaseLost:
                pass
        return True

    async def publish(self, release_id: str) -> dict:
        # No ready artifact left by a dead/expired attempt can be published.
        row = await self.storage._one("""
            SELECT r.* FROM knowledge.knowledge_release r
            JOIN knowledge.ingestion_job j ON j.job_id::text=r.evaluation->>'job_id'
            WHERE r.release_id=%s AND j.status='succeeded' AND j.kind='markdown_build'
              AND r.release_id='rel-' || j.job_id::text || '-' || j.attempts::text
            """, (release_id,))
        if row is None:
            raise StorageConflict("release has no completed build")
        self._match_manifest(row)
        await self.storage.activate_release(release_id)
        return {"release_id": release_id, "status": "published"}

    async def revoke(self, source_id: str, *, reason: str, revoked_by: str) -> dict:
        source = await self.storage._one("SELECT source_id FROM knowledge.source_document WHERE source_id=%s", (source_id,))
        if source is None:
            raise KnowledgeNotFound("source unavailable")
        await self.storage.revoke_source(source_id, reason=reason, revoked_by=revoked_by)
        return {"source_id": source_id, "revoked": True}


@asynccontextmanager
async def open_knowledge_runtime(config: Settings | None = None):
    """One autocommit psycopg connection per request/worker operation; no fallback."""
    config = config or settings
    if not config.rag_v2_enabled or not config.knowledge_database_url:
        raise KnowledgeUnavailable("knowledge service is disabled or unconfigured")
    try:
        connection = await AsyncConnection.connect(config.knowledge_database_url, autocommit=True,
            connect_timeout=config.knowledge_database_timeout_seconds,
            options=f"-c statement_timeout={config.knowledge_database_timeout_seconds * 1000}")
    except Exception as exc:
        raise KnowledgeUnavailable("knowledge database unavailable") from exc
    async with connection:
        yield KnowledgeRuntime(KnowledgeStorage(connection), config)
