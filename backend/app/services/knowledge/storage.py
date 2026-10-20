"""RAG v2 PostgreSQL repository (psycopg 3, no ORM or implicit migrations).

API contract
------------
The caller owns a dedicated ``AsyncConnection`` opened with ``autocommit=True``
and READ COMMITTED (the PostgreSQL default). Do not share it concurrently. Each
write method owns its transaction; do not wrap repository calls in an outer
transaction. This keeps revocation checks on fresh snapshots. No DSN/config is
loaded and no connection or migration is started at import time.

This first version is ONE SHARED CORPUS for authenticated users. API handlers must
require login for reads and admin privileges for all writes/build reads. There
is deliberately no client ``filters``/tenant/ACL parameter that could masquerade
as authorization. ``source_ids`` only narrows exact retrieval; it never grants
access. Private corpora require a separate, end-to-end authorization design.

Build flow: create_source -> add_version -> add_span -> create_release ->
add_chunk (+ optional wiki drafts/claims/dependencies/review) -> mark_ready ->
activate_release. A manifest fixes model/revision/dimension/normalization and
checksums. Failed builds never change the active pointer. Records and completed
release artifacts are immutable. activate_release also performs rollback to a
previously published release; source revocations remain append-only and global.

pin_active_release once per request, then pass its release_id to list_evidence,
search_dense, get_citation, and list_wiki_claims. Published old citations remain
resolvable. All these reads recheck revocation and [valid_from, valid_until), in
UTC-aware timestamptz. Before answer emission re-fetch selected citations and
wiki dependencies: a source can be revoked while a model is running. Materialized
BM25 candidates/caches MUST be intersected with a fresh list_evidence result
before ranking/output. This module provides candidates, not BM25 itself.

mark_ready hashes the persisted chunk inventory and the supplied BM25 artifact
bytes; the compiler remains responsible for actually building/testing that
artifact and for evaluation policy. SQL independently enforces count, review,
foreign keys, dimensions and release transitions. No model/network calls occur.
Job claim/heartbeat/finish use database time and a fresh UUID fencing token per
attempt. Expired owners cannot renew or finish, even if worker names are reused.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any
from uuid import UUID, uuid4

from psycopg import AsyncConnection, IsolationLevel
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class StorageConflict(ValueError):
    """Immutable identity/idempotency key reused with different content/state."""


class LeaseLost(StorageConflict):
    """The job attempt expired or was superseded; its output must be discarded."""


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{field} must be nonempty text without NUL")
    return value


def _sha(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("checksum must be a lowercase SHA-256 digest")
    return value


def _positive(value: int, field: str, maximum: int = 2_147_483_647) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{field} must be an integer in [1, {maximum}]")
    return value


def _json_object(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("metadata/payload must be a JSON object")
    result = dict(value)
    if any(not isinstance(key, str) for key in result):
        raise ValueError("JSON object keys must be strings")
    # JSON round-trip also prevents later caller mutation and rejects NaN/Infinity.
    return json.loads(json.dumps(result, allow_nan=False))


def _timestamp(value: datetime | None) -> datetime | None:
    if value is not None and (not isinstance(value, datetime) or value.utcoffset() is None):
        raise ValueError("timestamps must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    embedding_model: str
    embedding_revision: str
    embedding_dim: int
    embedding_normalized: bool
    expected_chunks: int
    corpus_sha256: str
    bm25_sha256: str
    distance_metric: str = "cosine"

    def __post_init__(self) -> None:
        _text(self.embedding_model, "embedding_model")
        _text(self.embedding_revision, "embedding_revision")
        _positive(self.embedding_dim, "embedding_dim", 16000)
        _positive(self.expected_chunks, "expected_chunks")
        if not isinstance(self.embedding_normalized, bool):
            raise ValueError("embedding_normalized must be boolean")
        if self.distance_metric != "cosine":
            raise ValueError("only cosine distance is supported")
        _sha(self.corpus_sha256)
        _sha(self.bm25_sha256)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ReleaseManifest:
        return cls(**{name: row[name] for name in cls.__dataclass_fields__})


def vector_literal(values: Sequence[float], manifest: ReleaseManifest) -> str:
    """Validate before sending a bound ``%s::public.vector`` parameter.

    Finite float32-representable, nonzero vectors only. Unit vectors are required
    when fixed by the manifest (0.001 tolerance, also checked after DB rounding).
    """
    if len(values) != manifest.embedding_dim:
        raise ValueError(f"embedding dimension must be {manifest.embedding_dim}")
    numbers = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError("embedding components must be numbers")
        try:
            number = float(value)
        except (OverflowError, ValueError) as exc:
            raise ValueError("embedding components must fit float32") from exc
        if not math.isfinite(number) or abs(number) > 3.4028234663852886e38:
            raise ValueError("embedding components must be finite float32 values")
        numbers.append(number)
    norm = math.hypot(*numbers)
    if norm < 1.1754943508222875e-38:
        raise ValueError("embedding must have nonzero float32 norm")
    if manifest.embedding_normalized and abs(norm - 1) > 0.001:
        raise ValueError("embedding must be unit normalized")
    return "[" + ",".join(format(number, ".17g") for number in numbers) + "]"


def corpus_checksum(chunks: Sequence[Mapping[str, Any]]) -> str:
    """Hash canonical inventory, independent of order and vector float rounding.

    Each chunk supplies chunk_id/span_id/version_id/content/token_count. Vectors
    are persisted once under the immutable model manifest, rather than serialized
    through a second lossy float conversion for this inventory checksum.
    """
    fields = ("chunk_id", "span_id", "version_id", "content", "token_count")
    inventory = []
    seen = set()
    for chunk in chunks:
        record = {name: chunk[name] for name in fields}
        for name in fields[:-1]:
            _text(record[name], name)
        _positive(record["token_count"], "token_count")
        if record["chunk_id"] in seen:
            raise ValueError("duplicate chunk_id in corpus manifest")
        seen.add(record["chunk_id"])
        inventory.append(record)
    encoded = json.dumps(sorted(inventory, key=lambda item: item["chunk_id"]),
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# Shared scope is fixed in SQL, not taken from client filters. Each statement
# independently checks the global barrier, including historical citation reads.
EVIDENCE_SQL = """
SELECT c.release_id, c.chunk_id, c.span_id, c.version_id, c.content, c.token_count,
       s.original_text, s.locator, s.section_path, d.source_id, d.title, d.metadata,
       d.content_sha256, d.valid_from::text AS valid_from, d.valid_until::text AS valid_until
FROM knowledge.retrieval_chunk c
JOIN knowledge.knowledge_release r ON r.release_id = c.release_id
JOIN knowledge.evidence_span s ON s.span_id = c.span_id AND s.version_id = c.version_id
JOIN knowledge.document_version d ON d.version_id = c.version_id
WHERE c.release_id = %s AND r.status = 'published'
  AND d.valid_from <= statement_timestamp() AND statement_timestamp() < d.valid_until
  AND NOT EXISTS (SELECT 1 FROM knowledge.source_revocation revoked
                  WHERE revoked.source_id = d.source_id)
"""

DENSE_SQL = """
WITH eligible AS MATERIALIZED (
    SELECT c.chunk_id, c.span_id, c.version_id, c.content, c.embedding, d.source_id
    FROM knowledge.retrieval_chunk c
    JOIN knowledge.document_version d ON d.version_id = c.version_id
    JOIN knowledge.knowledge_release r ON r.release_id = c.release_id
    WHERE c.release_id = %s AND r.status = 'published'
      AND d.valid_from <= statement_timestamp() AND statement_timestamp() < d.valid_until
      AND NOT EXISTS (SELECT 1 FROM knowledge.source_revocation revoked
                      WHERE revoked.source_id = d.source_id)
      AND (%s::text[] IS NULL OR d.source_id = ANY(%s::text[]))
)
SELECT chunk_id, span_id, version_id, content, source_id,
       embedding OPERATOR(public.<=>) %s::public.vector AS distance
FROM eligible ORDER BY distance, chunk_id LIMIT %s
"""

WIKI_SQL = """
SELECT c.claim_id, c.draft_id, c.claim_text, c.conditions, w.title, w.body,
       (SELECT jsonb_agg(jsonb_build_object('span_id', dep.span_id, 'version_id', dep.version_id)
                         ORDER BY dep.span_id)
        FROM knowledge.claim_dependency dep
        WHERE dep.release_id = c.release_id AND dep.claim_id = c.claim_id) AS dependencies
FROM knowledge.wiki_claim c
JOIN knowledge.wiki_draft w ON w.release_id = c.release_id AND w.draft_id = c.draft_id
JOIN knowledge.knowledge_release r ON r.release_id = c.release_id
WHERE c.release_id = %s AND r.status = 'published' AND w.status = 'approved'
  AND EXISTS (SELECT 1 FROM knowledge.claim_dependency dep
              WHERE dep.release_id = c.release_id AND dep.claim_id = c.claim_id)
  AND NOT EXISTS (
      SELECT 1 FROM knowledge.claim_dependency dep
      JOIN knowledge.document_version d ON d.version_id = dep.version_id
      WHERE dep.release_id = c.release_id
        -- Suppress the WHOLE draft if any claim's source becomes unavailable;
        -- returning its body with only safe claims could leak revoked content.
        AND dep.claim_id IN (SELECT sibling.claim_id FROM knowledge.wiki_claim sibling
            WHERE sibling.release_id = c.release_id AND sibling.draft_id = c.draft_id)
        AND (d.valid_from > statement_timestamp() OR statement_timestamp() >= d.valid_until
             OR EXISTS (SELECT 1 FROM knowledge.source_revocation revoked
                        WHERE revoked.source_id = d.source_id))
  )
ORDER BY c.draft_id, c.claim_id
"""


class KnowledgeStorage:
    """Parameterized repository; returns dictionaries with explicit SQL columns.

    ``pin_active_release`` returns the release row (including manifest), or None.
    ``list_evidence`` returns ALL currently usable chunks, ordered by chunk_id,
    for service-layer BM25. ``get_citation`` resolves an original span in a
    published release, or None when absent/expired/revoked. ``search_dense``
    returns exact cosine distances (smaller is better), never a probability.
    Source versions accept arbitrary immutable version IDs plus a bytes hash;
    existing domain.Evidence.doc_version SHA-256 IDs can be used directly.
    """

    def __init__(self, connection: AsyncConnection):
        if not connection.autocommit or connection.isolation_level not in (None, IsolationLevel.READ_COMMITTED):
            raise ValueError("use autocommit=True and READ COMMITTED for fresh revocation snapshots")
        self.connection = connection

    def _idle(self) -> None:
        if self.connection.info.transaction_status != TransactionStatus.IDLE:
            raise RuntimeError("repository requires an idle, exclusively owned connection")

    async def _rows(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        async with self.connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(sql, params)
            return await cursor.fetchall()

    async def _one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        rows = await self._rows(sql, params)
        return rows[0] if rows else None

    async def create_source(self, source_id: str, doc_id: str, source_uri: str) -> None:
        """Register immutable logical identity. Duplicate identities fail explicitly."""
        self._idle()
        await self.connection.execute(
            "INSERT INTO knowledge.source_document(source_id, doc_id, source_uri) VALUES (%s,%s,%s)",
            (_text(source_id, "source_id"), _text(doc_id, "doc_id"), _text(source_uri, "source_uri")))

    async def add_version(self, version_id: str, source_id: str, original_content: bytes,
                          title: str, *, metadata: Mapping[str, Any] | None = None,
                          valid_from: datetime | None = None,
                          valid_until: datetime | None = None) -> None:
        """Persist original bytes, hash and immutable provenance. Validity is [start,end)."""
        self._idle()
        if not isinstance(original_content, bytes) or not original_content:
            raise ValueError("original_content must be nonempty bytes")
        _timestamp(valid_from)
        _timestamp(valid_until)
        if valid_from is not None and valid_until is not None and valid_from >= valid_until:
            raise ValueError("valid_from must precede valid_until")
        await self.connection.execute("""
            INSERT INTO knowledge.document_version
                (version_id, source_id, content_sha256, original_content, title, metadata, valid_from, valid_until)
            VALUES (%s,%s,%s,%s,%s,%s,COALESCE(%s::timestamptz,'-infinity'),
                    COALESCE(%s::timestamptz,'infinity'))
            """, (_text(version_id, "version_id"), _text(source_id, "source_id"),
                   hashlib.sha256(original_content).hexdigest(), original_content, _text(title, "title"),
                   Jsonb(_json_object(metadata if metadata is not None else {})), valid_from, valid_until))

    async def add_span(self, span_id: str, version_id: str, original_text: str,
                       locator: Mapping[str, Any], section_path: Sequence[str] = ()) -> None:
        """Store parser-supplied original locator; no generated content is substituted."""
        self._idle()
        if isinstance(section_path, str) or any(not isinstance(part, str) for part in section_path):
            raise ValueError("section_path must be a sequence of strings")
        location = _json_object(locator)
        if not location:
            raise ValueError("locator must identify an original source location")
        await self.connection.execute("""
            INSERT INTO knowledge.evidence_span(span_id,version_id,original_text,locator,section_path)
            VALUES (%s,%s,%s,%s,%s)
            """, (_text(span_id, "span_id"), _text(version_id, "version_id"),
                   _text(original_text, "original_text"), Jsonb(location), Jsonb(list(section_path))))

    async def create_release(self, release_id: str, manifest: ReleaseManifest,
                             *, evaluation: Mapping[str, Any] | None = None) -> None:
        self._idle()
        await self.connection.execute("""
            INSERT INTO knowledge.knowledge_release
                (release_id,embedding_model,embedding_revision,embedding_dim,embedding_normalized,
                 distance_metric,expected_chunks,corpus_sha256,bm25_sha256,evaluation)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (_text(release_id, "release_id"), manifest.embedding_model, manifest.embedding_revision,
                   manifest.embedding_dim, manifest.embedding_normalized, manifest.distance_metric,
                   manifest.expected_chunks, manifest.corpus_sha256, manifest.bm25_sha256,
                   Jsonb(_json_object(evaluation if evaluation is not None else {}))))

    async def _release(self, release_id: str, *, lock: bool = False) -> dict[str, Any]:
        # Only this constant suffix varies; identifiers/values are never interpolated.
        query = "SELECT * FROM knowledge.knowledge_release WHERE release_id = %s"
        if lock:
            query += " FOR UPDATE"
        row = await self._one(query, (_text(release_id, "release_id"),))
        if row is None:
            raise StorageConflict("unknown knowledge release")
        return row

    async def add_chunk(self, release_id: str, chunk_id: str, span_id: str,
                        version_id: str, content: str, token_count: int,
                        embedding: Sequence[float]) -> None:
        self._idle()
        async with self.connection.transaction():
            row = await self._release(release_id)
            literal = vector_literal(embedding, ReleaseManifest.from_row(row))
            await self.connection.execute("""
                INSERT INTO knowledge.retrieval_chunk
                    (release_id,chunk_id,span_id,version_id,content,token_count,embedding)
                VALUES (%s,%s,%s,%s,%s,%s,%s::public.vector)
                """, (release_id, _text(chunk_id, "chunk_id"), _text(span_id, "span_id"),
                       _text(version_id, "version_id"), _text(content, "content"),
                       _positive(token_count, "token_count"), literal))

    async def mark_ready(self, release_id: str, bm25_artifact: bytes) -> None:
        """Verify persisted inventory and artifact bytes, then freeze the build."""
        self._idle()
        if not isinstance(bm25_artifact, bytes) or not bm25_artifact:
            raise ValueError("BM25 artifact must be nonempty bytes")
        async with self.connection.transaction():
            release = await self._release(release_id, lock=True)
            if release["status"] != "building":
                raise StorageConflict("only a building release can become ready")
            chunks = await self._rows("""
                SELECT chunk_id,span_id,version_id,content,token_count
                FROM knowledge.retrieval_chunk WHERE release_id = %s
                """, (release_id,))
            if len(chunks) != release["expected_chunks"] or corpus_checksum(chunks) != release["corpus_sha256"]:
                raise StorageConflict("release inventory count/checksum mismatch")
            if hashlib.sha256(bm25_artifact).hexdigest() != release["bm25_sha256"]:
                raise StorageConflict("BM25 artifact checksum mismatch")
            await self.connection.execute(
                "UPDATE knowledge.knowledge_release SET status = 'ready' WHERE release_id = %s", (release_id,))

    async def fail_release(self, release_id: str) -> None:
        self._idle()
        row = await self._one("""
            UPDATE knowledge.knowledge_release SET status = 'failed'
            WHERE release_id = %s AND status = 'building' RETURNING release_id
            """, (_text(release_id, "release_id"),))
        if row is None:
            raise StorageConflict("only a building release can fail")

    async def activate_release(self, release_id: str) -> None:
        """Atomically publish/switch; the same method rolls back published releases."""
        self._idle()
        async with self.connection.transaction():
            # Serialize even the very first activation when the singleton row is absent.
            await self.connection.execute("SELECT pg_advisory_xact_lock(%s)", (64197233002,))
            row = await self._release(release_id, lock=True)
            if row["status"] not in ("ready", "published"):
                raise StorageConflict("release is not ready for publication")
            if row["status"] == "ready":
                await self.connection.execute(
                    "UPDATE knowledge.knowledge_release SET status = 'published' WHERE release_id = %s", (release_id,))
            await self.connection.execute("""
                INSERT INTO knowledge.active_release(scope,release_id) VALUES ('shared',%s)
                ON CONFLICT (scope) DO UPDATE
                SET release_id = EXCLUDED.release_id, switched_at = clock_timestamp()
                """, (release_id,))

    async def pin_active_release(self) -> dict[str, Any] | None:
        self._idle()
        return await self._one("""
            SELECT r.* FROM knowledge.active_release a
            JOIN knowledge.knowledge_release r ON r.release_id = a.release_id
            WHERE a.scope = 'shared' AND r.status = 'published'
            """)

    async def list_evidence(self, release_id: str) -> list[dict[str, Any]]:
        self._idle()
        return await self._rows(EVIDENCE_SQL + " ORDER BY c.chunk_id", (_text(release_id, "release_id"),))

    async def get_citation(self, release_id: str, span_id: str) -> dict[str, Any] | None:
        """Return original text/locator, never an unprotected file path or source URI."""
        self._idle()
        return await self._one(EVIDENCE_SQL + " AND s.span_id = %s ORDER BY c.chunk_id LIMIT 1",
                               (_text(release_id, "release_id"), _text(span_id, "span_id")))

    async def search_dense(self, release_id: str, embedding: Sequence[float], *,
                           embedding_model: str, embedding_revision: str,
                           limit: int = 20, source_ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
        """Rank the eligible set exactly; no full-corpus top-k then post-filter."""
        self._idle()
        _positive(limit, "limit", 1000)
        sources = None
        if source_ids is not None:
            if isinstance(source_ids, str):
                raise ValueError("source_ids must be a sequence, not a string")
            sources = [_text(item, "source_id") for item in source_ids]
        async with self.connection.transaction():
            release = await self._release(release_id)
            manifest = ReleaseManifest.from_row(release)
            if (embedding_model, embedding_revision) != (manifest.embedding_model, manifest.embedding_revision):
                raise ValueError("query embedding model/revision differs from release")
            literal = vector_literal(embedding, manifest)
            return await self._rows(DENSE_SQL, (release_id, sources, sources, literal, limit))

    async def revoke_source(self, source_id: str, *, reason: str, revoked_by: str) -> None:
        """Idempotent append-only barrier; no restore/delete endpoint exists."""
        self._idle()
        await self.connection.execute("""
            INSERT INTO knowledge.source_revocation(source_id,reason,revoked_by) VALUES (%s,%s,%s)
            ON CONFLICT (source_id) DO NOTHING
            """, (_text(source_id, "source_id"), _text(reason, "reason"), _text(revoked_by, "revoked_by")))

    async def add_wiki_draft(self, release_id: str, draft_id: str, *, title: str,
                             body: str, compiler_model: str, prompt_revision: str) -> None:
        self._idle()
        await self.connection.execute("""
            INSERT INTO knowledge.wiki_draft
                (release_id,draft_id,title,body,compiler_model,prompt_revision)
            VALUES (%s,%s,%s,%s,%s,%s)
            """, tuple(_text(value, "wiki draft field") for value in
                       (release_id, draft_id, title, body, compiler_model, prompt_revision)))

    async def add_wiki_claim(self, release_id: str, claim_id: str, draft_id: str,
                             claim_text: str, *, dependencies: Sequence[tuple[str, str]],
                             conditions: Mapping[str, Any] | None = None) -> None:
        """Insert a claim and all (span_id, version_id) dependencies atomically."""
        self._idle()
        if not dependencies or len(set(dependencies)) != len(dependencies):
            raise ValueError("claims require nonempty, unique dependencies")
        pairs = [(_text(span, "span_id"), _text(version, "version_id")) for span, version in dependencies]
        async with self.connection.transaction():
            await self.connection.execute("""
                INSERT INTO knowledge.wiki_claim(release_id,claim_id,draft_id,claim_text,conditions)
                VALUES (%s,%s,%s,%s,%s)
                """, (_text(release_id, "release_id"), _text(claim_id, "claim_id"),
                       _text(draft_id, "draft_id"), _text(claim_text, "claim_text"),
                       Jsonb(_json_object(conditions if conditions is not None else {}))))
            async with self.connection.cursor() as cursor:
                await cursor.executemany("""
                    INSERT INTO knowledge.claim_dependency(release_id,claim_id,span_id,version_id)
                    VALUES (%s,%s,%s,%s)
                    """, [(release_id, claim_id, span, version) for span, version in pairs])

    async def review_wiki_draft(self, release_id: str, draft_id: str, *, approved: bool) -> None:
        self._idle()
        if not isinstance(approved, bool):
            raise ValueError("approved must be boolean")
        row = await self._one("""
            UPDATE knowledge.wiki_draft SET status = %s
            WHERE release_id = %s AND draft_id = %s AND status = 'draft' RETURNING draft_id
            """, ("approved" if approved else "rejected", _text(release_id, "release_id"), _text(draft_id, "draft_id")))
        if row is None:
            raise StorageConflict("unknown draft or review already finalized")

    async def list_wiki_claims(self, release_id: str) -> list[dict[str, Any]]:
        self._idle()
        return await self._rows(WIKI_SQL, (_text(release_id, "release_id"),))

    async def enqueue_job(self, idempotency_key: str, kind: str, payload: Mapping[str, Any], *,
                          max_attempts: int = 3) -> dict[str, Any]:
        """Same key+kind+payload+retry budget returns existing job; mismatches fail."""
        self._idle()
        data = _json_object(payload)
        _text(idempotency_key, "idempotency_key")
        _text(kind, "kind")
        _positive(max_attempts, "max_attempts", 100)
        async with self.connection.transaction():
            await self.connection.execute("""
                INSERT INTO knowledge.ingestion_job(job_id,idempotency_key,kind,payload,max_attempts)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT (idempotency_key) DO NOTHING
                """, (uuid4(), idempotency_key, kind, Jsonb(data), max_attempts))
            job = await self._one("SELECT * FROM knowledge.ingestion_job WHERE idempotency_key = %s",
                                  (idempotency_key,))
            if job is None or (job["kind"], job["payload"], job["max_attempts"]) != (kind, data, max_attempts):
                raise StorageConflict("idempotency key reused with different job content")
            return job

    async def claim_job(self, worker: str, *, lease_seconds: int = 60) -> dict[str, Any] | None:
        """Recover expired attempts with SKIP LOCKED; exhausted jobs become failed."""
        self._idle()
        _text(worker, "worker")
        _positive(lease_seconds, "lease_seconds", 86400)
        async with self.connection.transaction():
            # Lock expired exhausted rows without waiting on another worker's claims.
            await self.connection.execute("""
                WITH exhausted AS (
                    SELECT job_id FROM knowledge.ingestion_job
                    WHERE status = 'running' AND lease_until <= clock_timestamp()
                      AND attempts >= max_attempts FOR UPDATE SKIP LOCKED
                )
                UPDATE knowledge.ingestion_job j SET status = 'failed', lease_owner = NULL,
                    lease_token = NULL, lease_until = NULL, finished_at = clock_timestamp(),
                    last_error = 'lease expired after final attempt'
                FROM exhausted e WHERE j.job_id = e.job_id
                """)
            return await self._one("""
                WITH candidate AS (
                    SELECT job_id FROM knowledge.ingestion_job
                    WHERE attempts < max_attempts AND
                        ((status = 'queued' AND available_at <= clock_timestamp()) OR
                         (status = 'running' AND lease_until <= clock_timestamp()))
                    ORDER BY available_at, created_at, job_id FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE knowledge.ingestion_job j SET status = 'running', attempts = attempts + 1,
                    lease_owner = %s, lease_token = %s,
                    lease_until = clock_timestamp() + %s * interval '1 second',
                    heartbeat_at = clock_timestamp(), finished_at = NULL
                FROM candidate c WHERE j.job_id = c.job_id RETURNING j.*
                """, (worker, uuid4(), lease_seconds))

    async def heartbeat_job(self, job_id: UUID, lease_token: UUID, *, lease_seconds: int = 60) -> dict[str, Any]:
        self._idle()
        _positive(lease_seconds, "lease_seconds", 86400)
        row = await self._one("""
            UPDATE knowledge.ingestion_job SET heartbeat_at = clock_timestamp(),
                lease_until = clock_timestamp() + %s * interval '1 second'
            WHERE job_id = %s AND lease_token = %s AND status = 'running'
                AND lease_until > clock_timestamp() RETURNING *
            """, (lease_seconds, job_id, lease_token))
        if row is None:
            raise LeaseLost("job lease expired or was replaced")
        return row

    async def finish_job(self, job_id: UUID, lease_token: UUID, *, error: str | None = None,
                         retry_seconds: int = 30) -> dict[str, Any]:
        """Complete or retry current attempt; errors must be sanitized (no secrets)."""
        self._idle()
        _positive(retry_seconds, "retry_seconds", 86400)
        if error is not None:
            _text(error, "error")
        row = await self._one("""
            UPDATE knowledge.ingestion_job SET
                status = CASE WHEN %s::text IS NULL THEN 'succeeded'
                              WHEN attempts < max_attempts THEN 'queued' ELSE 'failed' END,
                available_at = clock_timestamp() + %s * interval '1 second',
                finished_at = CASE WHEN %s::text IS NULL OR attempts >= max_attempts
                                   THEN clock_timestamp() ELSE NULL END,
                last_error = %s, lease_owner = NULL, lease_token = NULL, lease_until = NULL
            WHERE job_id = %s AND lease_token = %s AND status = 'running'
                AND lease_until > clock_timestamp() RETURNING *
            """, (error, retry_seconds, error, error[:2000] if error is not None else None, job_id, lease_token))
        if row is None:
            raise LeaseLost("job lease expired or was replaced")
        return row
