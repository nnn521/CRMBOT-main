"""Pure validation/SQL contracts, plus an explicitly opt-in real pgvector lifecycle.

No DB is contacted unless TEST_KNOWLEDGE_DATABASE_URL is explicitly supplied.
That DSN MUST identify a disposable database with NO knowledge schema. The real
integration test creates and drops only its own knowledge schema; never point it
at an application/production database. SQL text tests are not DB validation.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import inspect
import os
from pathlib import Path
import sys

import pytest

from app.services.knowledge.storage import (
    DENSE_SQL, EVIDENCE_SQL, WIKI_SQL, KnowledgeStorage, LeaseLost, ReleaseManifest,
    StorageConflict, _json_object, _positive, _timestamp, corpus_checksum, vector_literal,
)


BACKEND = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("knowledge_migration_runner", BACKEND / "scripts" / "migrate_knowledge.py")
assert _SPEC is not None and _SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = RUNNER
_SPEC.loader.exec_module(RUNNER)
SQL = (BACKEND / "migrations" / "knowledge" / "001_initial.sql").read_text(encoding="utf-8")
CHUNK = {"chunk_id": "c1", "span_id": "s1", "version_id": "v1", "content": "原始证据", "token_count": 4}
ARTIFACT = b"versioned-bm25-artifact"


def manifest(**overrides):
    fields = dict(embedding_model="bge-m3", embedding_revision="frozen-revision",
                  embedding_dim=3, embedding_normalized=True, expected_chunks=1,
                  corpus_sha256=corpus_checksum([CHUNK]),
                  bm25_sha256=hashlib.sha256(ARTIFACT).hexdigest())
    fields.update(overrides)
    return ReleaseManifest(**fields)


@pytest.mark.parametrize("field,value", [
    ("embedding_model", ""), ("embedding_revision", " "), ("embedding_dim", 0),
    ("embedding_dim", True), ("embedding_dim", 16001), ("expected_chunks", 0),
    ("embedding_normalized", 1), ("distance_metric", "euclidean"),
    ("corpus_sha256", "ABC"), ("bm25_sha256", "g" * 64),
])
def test_manifest_rejects_ambiguous_or_incomplete_embedding_space(field, value):
    with pytest.raises(ValueError):
        manifest(**{field: value})


def test_manifest_is_frozen_and_round_trips_release_row():
    item = manifest()
    row = {key: getattr(item, key) for key in item.__dataclass_fields__}
    row.update(release_id="r1", status="building")
    assert ReleaseManifest.from_row(row) == item
    with pytest.raises(AttributeError):
        item.embedding_revision = "changed"


@pytest.mark.parametrize("vector", [
    [1, 0], [0, 0, 0], [float("nan"), 0, 1], [float("inf"), 0, 1],
    [True, 0, 0], ["1", 0, 0], [2, 0, 0], [1e40, 0, 0], [1e-60, 0, 0],
    [10 ** 500, 0, 0],
])
def test_vectors_fail_before_sql_for_dimension_nonfinite_zero_or_wrong_norm(vector):
    with pytest.raises(ValueError):
        vector_literal(vector, manifest())


def test_vector_binding_does_not_require_pgvector_python_dependency():
    assert vector_literal([1, 0, 0], manifest()) == "[1,0,0]"
    assert vector_literal([2, 0, 0], manifest(embedding_normalized=False)) == "[2,0,0]"
    assert vector_literal([1, 0], manifest(embedding_dim=2)) == "[1,0]"


def test_corpus_hash_is_order_independent_but_sensitive_to_provenance_and_content():
    second = dict(CHUNK, chunk_id="c2", span_id="s2")
    assert corpus_checksum([CHUNK, second]) == corpus_checksum([second, CHUNK])
    for key, value in (("span_id", "new-source-span"), ("version_id", "v2"),
                       ("content", "changed"), ("token_count", 5)):
        assert corpus_checksum([CHUNK]) != corpus_checksum([dict(CHUNK, **{key: value})])
    with pytest.raises(ValueError, match="duplicate"):
        corpus_checksum([CHUNK, CHUNK])


def test_json_and_time_validation_reject_nonportable_values():
    nested = {"array": [1, {"name": "原文"}]}
    copied = _json_object(nested)
    nested["array"].append(2)
    assert copied == {"array": [1, {"name": "原文"}]}
    for value in ([1], {"bad": float("nan")}, {1: "wrong-key"}):
        with pytest.raises((ValueError, TypeError)):
            _json_object(value)
    with pytest.raises(ValueError, match="timezone-aware"):
        _timestamp(datetime(2026, 1, 1))
    assert _timestamp(datetime(2026, 1, 1, tzinfo=timezone.utc)) is not None
    for value in (True, 0, -1, 1.5):
        with pytest.raises(ValueError):
            _positive(value, "lease")


def test_migration_discovery_is_backend_anchored_and_hashes_exact_bytes():
    migrations = RUNNER.discover_migrations()
    assert [item.filename for item in migrations] == ["001_initial.sql"]
    assert migrations[0].checksum == hashlib.sha256(
        (BACKEND / "migrations" / "knowledge" / "001_initial.sql").read_bytes()).hexdigest()
    assert RUNNER.pending_migrations(migrations, {}) == migrations
    applied = {item.version: (item.filename, item.checksum) for item in migrations}
    assert RUNNER.pending_migrations(migrations, applied) == ()
    with pytest.raises(RUNNER.MigrationError, match="checksum"):
        RUNNER.pending_migrations(migrations, {"001": ("001_initial.sql", "0" * 64)})
    with pytest.raises(RUNNER.MigrationError, match="missing"):
        RUNNER.pending_migrations(migrations, {"999": ("999_missing.sql", "0" * 64)})


def test_migration_rejects_duplicate_versions_and_backfilled_history(tmp_path):
    (tmp_path / "001_a.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "001_b.sql").write_text("SELECT 2;", encoding="utf-8")
    with pytest.raises(RUNNER.MigrationError, match="duplicate"):
        RUNNER.discover_migrations(tmp_path)
    old = RUNNER.discover_migrations()[0]
    new = replace(old, version="002", filename="002_later.sql")
    with pytest.raises(RUNNER.MigrationError, match="before"):
        RUNNER.pending_migrations((old, new), {"002": (new.filename, new.checksum)})


def test_migration_list_and_missing_dsn_never_connect(monkeypatch, capsys):
    monkeypatch.delenv("TEST_ABSENT_KNOWLEDGE_DSN", raising=False)
    assert RUNNER.main(["--list"]) == 0
    assert "001_initial.sql" in capsys.readouterr().out
    assert RUNNER.main(["--dsn-env", "TEST_ABSENT_KNOWLEDGE_DSN"]) == 1
    assert "no database was contacted" in capsys.readouterr().err


def test_migration_runner_locks_and_records_inside_single_transaction():
    source = inspect.getsource(RUNNER.migrate)
    assert source.index("connection.transaction()") < source.index("pg_advisory_xact_lock")
    assert source.index("pg_advisory_xact_lock") < source.index("CREATE TABLE IF NOT EXISTS")
    assert "knowledge.schema_migrations" in source and "migration.checksum" in source
    assert "raise MigrationError" in source and "from exc" in source
    assert "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public" in SQL
    # No production tables are altered, truncated, replaced or deleted by DDL.
    assert "ALTER TABLE" not in SQL.upper()
    assert "DROP TABLE" not in SQL.upper() and "TRUNCATE" not in SQL.upper()


def test_sql_enforces_immutable_versions_build_fence_and_publication_gate():
    assert "embedding public.vector NOT NULL" in SQL
    assert "public.vector_dims(NEW.embedding) <> manifest.embedding_dim" in SQL
    assert "embedding_dim BETWEEN 1 AND 16000" in SQL
    assert "release manifest is immutable" in SQL
    for table in ("source_document", "document_version", "evidence_span", "retrieval_chunk", "source_revocation"):
        assert f"BEFORE UPDATE OR DELETE ON knowledge.{table}" in SQL
    assert "WHERE release_id = NEW.release_id FOR SHARE" in SQL
    assert "manifest.status <> 'building'" in SQL
    assert "OLD.expected_chunks" in SQL and "release chunks are incomplete" in SQL
    assert "OLD.status = 'ready' AND NEW.status = 'published'" in SQL
    assert "active release must be fully built and published" in SQL
    assert "FOREIGN KEY (span_id, version_id)" in SQL


def test_all_evidence_paths_recheck_barrier_and_time_in_published_release():
    for query in (EVIDENCE_SQL, DENSE_SQL, WIKI_SQL):
        assert "knowledge.source_revocation" in query
        assert "statement_timestamp()" in query
        assert "r.status = 'published'" in query
    activate = inspect.getsource(KnowledgeStorage.activate_release)
    assert "source_revocation" not in activate
    assert "pg_advisory_xact_lock" in activate and "connection.transaction()" in activate
    assert "EVIDENCE_SQL" in inspect.getsource(KnowledgeStorage.get_citation)
    assert "sibling.draft_id = c.draft_id" in WIKI_SQL
    assert "claim dependency must belong to the same release" in SQL


def test_dense_is_filtered_exact_and_no_client_authorization_filters_exist():
    assert "eligible AS MATERIALIZED" in DENSE_SQL
    assert DENSE_SQL.index("source_revocation") < DENSE_SQL.index("ORDER BY distance")
    assert DENSE_SQL.index("d.source_id = ANY(%s::text[])") < DENSE_SQL.index("LIMIT %s")
    assert "OPERATOR(public.<=>) %s::public.vector" in DENSE_SQL
    assert "hnsw" not in SQL.lower() and "ivfflat" not in SQL.lower()
    for name in ("list_evidence", "search_dense", "get_citation", "list_wiki_claims"):
        assert "filters" not in inspect.signature(getattr(KnowledgeStorage, name)).parameters
    source = inspect.getsource(KnowledgeStorage.search_dense)
    assert "embedding_model, embedding_revision" in source


def test_jobs_have_fencing_expiry_and_nonblocking_recovery():
    assert "idempotency_key text NOT NULL UNIQUE" in SQL
    claim = inspect.getsource(KnowledgeStorage.claim_job)
    assert "FOR UPDATE SKIP LOCKED" in claim
    assert "uuid4()" in claim and "attempts < max_attempts" in claim
    assert "lease_until <= clock_timestamp()" in claim
    for method in (KnowledgeStorage.heartbeat_job, KnowledgeStorage.finish_job):
        source = inspect.getsource(method)
        assert "lease_token = %s" in source
        assert "lease_until > clock_timestamp()" in source
        assert "raise LeaseLost" in source


@pytest.mark.skipif(not os.environ.get("TEST_KNOWLEDGE_DATABASE_URL"),
                    reason="real PostgreSQL/pgvector not configured; SQL contract tests are not integration proof")
def test_real_postgres_pgvector_lifecycle():
    """No mocks: migration replay, publish, revocation, rollback, cosine and leases."""
    import psycopg

    async def exercise():
        dsn = os.environ["TEST_KNOWLEDGE_DATABASE_URL"]
        async with await psycopg.AsyncConnection.connect(dsn, autocommit=True, connect_timeout=10) as conn:
            exists = await conn.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'knowledge'")
            if await exists.fetchone():
                pytest.fail("integration requires disposable database WITHOUT knowledge schema; refusing to mutate it")
            owned_schema = False
            try:
                assert await RUNNER.migrate(conn) == ("001_initial.sql",)
                owned_schema = True
                assert await RUNNER.migrate(conn) == ()
                store = KnowledgeStorage(conn)
                await store.create_source("source", "document", "urn:test:document")
                await store.add_version("v1", "source", b"original", "title")
                await store.add_span("s1", "v1", "original", {"line_start": 1, "line_end": 1})
                await store.create_release("r1", manifest())
                with pytest.raises(StorageConflict):
                    await store.activate_release("r1")
                assert await store.pin_active_release() is None
                with pytest.raises(ValueError):
                    await store.add_chunk("r1", "bad", "s1", "v1", "bad", 1, [1, 0])
                await store.add_chunk("r1", **{key: value for key, value in CHUNK.items()
                                              if key not in ("span_id", "version_id")},
                                      span_id="s1", version_id="v1", embedding=[1, 0, 0])
                with pytest.raises(StorageConflict):
                    await store.mark_ready("r1", b"wrong-artifact")
                await store.mark_ready("r1", ARTIFACT)
                await store.activate_release("r1")
                assert (await store.pin_active_release())["release_id"] == "r1"
                assert (await store.get_citation("r1", "s1"))["original_text"] == "original"
                with pytest.raises(psycopg.Error):
                    await conn.execute("UPDATE knowledge.document_version SET title = 'changed' WHERE version_id = 'v1'")
                with pytest.raises(psycopg.Error):
                    await store.add_chunk("r1", "late", "s1", "v1", "late", 1, [1, 0, 0])
                results = await store.search_dense("r1", [1, 0, 0], embedding_model="bge-m3",
                                                   embedding_revision="frozen-revision")
                assert results[0]["distance"] == pytest.approx(0)
                assert await store.search_dense("r1", [1, 0, 0], embedding_model="bge-m3",
                                                 embedding_revision="frozen-revision", source_ids=[]) == []
                await store.create_release("r2", manifest())
                await store.add_chunk("r2", "c1", "s1", "v1", CHUNK["content"], 4, [1, 0, 0])
                await store.add_wiki_draft("r2", "wiki", title="wiki", body="derived body",
                                           compiler_model="compiler-revision", prompt_revision="p1")
                await store.add_wiki_claim("r2", "claim", "wiki", "supported claim",
                                           dependencies=[("s1", "v1")])
                with pytest.raises(psycopg.Error):
                    await store.mark_ready("r2", ARTIFACT)
                await store.review_wiki_draft("r2", "wiki", approved=True)
                await store.mark_ready("r2", ARTIFACT)
                await store.activate_release("r2")
                assert (await store.list_wiki_claims("r2"))[0]["claim_id"] == "claim"
                await store.revoke_source("source", reason="withdrawn", revoked_by="admin")
                assert await store.list_wiki_claims("r2") == []
                await store.activate_release("r1")
                assert await store.get_citation("r1", "s1") is None
                assert await store.list_evidence("r1") == []
                assert await store.search_dense("r1", [1, 0, 0], embedding_model="bge-m3",
                                                 embedding_revision="frozen-revision") == []
                job = await store.enqueue_job("unique-key", "ingest", {"source": "source"})
                assert (await store.enqueue_job("unique-key", "ingest", {"source": "source"}))["job_id"] == job["job_id"]
                with pytest.raises(StorageConflict):
                    await store.enqueue_job("unique-key", "ingest", {"source": "other"})
                first = await store.claim_job("worker")
                await conn.execute("UPDATE knowledge.ingestion_job SET lease_until = clock_timestamp() - interval '1 second' WHERE job_id = %s", (job["job_id"],))
                second = await store.claim_job("worker")
                assert first["lease_token"] != second["lease_token"]
                with pytest.raises(LeaseLost):
                    await store.finish_job(job["job_id"], first["lease_token"])
                assert (await store.finish_job(job["job_id"], second["lease_token"]))["status"] == "succeeded"
            finally:
                if owned_schema:
                    await conn.execute("DROP SCHEMA knowledge CASCADE")

    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(exercise())
    else:
        asyncio.run(exercise())
