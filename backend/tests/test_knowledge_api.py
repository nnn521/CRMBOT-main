"""API permissions/schema and opt-in real PostgreSQL build lifecycle.

No external model calls. Real integration runs ONLY with an explicit disposable
TEST_KNOWLEDGE_DATABASE_URL with no knowledge schema; it owns/cleans that schema.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
import importlib.util
import os
from pathlib import Path
import sys
from uuid import uuid4

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.v1 import knowledge as api
from app.core.config import Settings
from app.services.auth import get_current_user
from app.services.knowledge.domain import document_fingerprint
from app.services.knowledge.runtime import (
    KnowledgeRuntime, KnowledgeUnavailable, RevisionEmbeddingClient,
    _original_evidence, open_knowledge_runtime,
)


REVISION = "sha256:" + "a" * 64


def config(**overrides):
    fields = dict(_env_file=None, rag_v2_enabled=True, knowledge_database_url="postgresql://unused",
                  knowledge_embedding_dimension=3, knowledge_embedding_revision=REVISION,
                  knowledge_upload_max_bytes=1000)
    fields.update(overrides)
    return Settings(**fields)


def app_for(role: str | None = "sales") -> FastAPI:
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    if role:
        app.dependency_overrides[get_current_user] = lambda: {"user_id": 7, "role": role, "username": "test"}
    return app


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/status", None), ("GET", "/search?q=test", None),
    ("GET", "/releases/rel/citations/" + "a" * 64, None),
    ("GET", "/sources", None), ("POST", "/sources", {"doc_id": "d", "source_uri": "urn:d"}),
    ("POST", "/sources/src/versions", None),
    ("POST", "/builds", {"version_ids": ["a" * 64], "idempotency_key": "key"}),
    ("GET", "/builds/" + str(uuid4()), None),
    ("POST", "/releases/rel/publish", None), ("POST", "/sources/src/revoke", {"reason": "withdraw"}),
])
def test_every_endpoint_requires_login_before_storage(monkeypatch, method, path, body):
    @asynccontextmanager
    async def forbidden():
        pytest.fail("unauthenticated request reached storage")
        yield
    monkeypatch.setattr(api, "open_knowledge_runtime", forbidden)
    with TestClient(app_for(None)) as client:
        response = client.request(method, "/api/v1/knowledge" + path, json=body)
    assert response.status_code == 401


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/sources", None), ("POST", "/sources", {"doc_id": "d", "source_uri": "urn:d"}),
    ("POST", "/sources/src/versions", None),
    ("POST", "/builds", {"version_ids": ["a" * 64], "idempotency_key": "key"}),
    ("GET", "/builds/" + str(uuid4()), None),
    ("POST", "/releases/rel/publish", None), ("POST", "/sources/src/revoke", {"reason": "withdraw"}),
])
def test_all_management_requires_database_admin_role(monkeypatch, method, path, body):
    @asynccontextmanager
    async def forbidden():
        pytest.fail("sales user reached management storage")
        yield
    monkeypatch.setattr(api, "open_knowledge_runtime", forbidden)
    with TestClient(app_for()) as client:
        response = client.request(method, "/api/v1/knowledge" + path, json=body)
    assert response.status_code == 403


def test_disabled_status_schema_and_readiness_never_connect(monkeypatch):
    monkeypatch.setattr(api.settings, "rag_v2_enabled", False)
    with TestClient(app_for()) as client:
        response = client.get("/api/v1/knowledge/status")
        assert response.status_code == 200
        assert response.json() == {"enabled": False, "ready": False, "release_id": None,
                                   "embedding_compatible": False, "scope": "shared_authenticated"}
    assert asyncio.run(api.readiness()) == {"enabled": False, "ready": True, "status": "disabled"}


def test_database_errors_do_not_return_dsn_or_key(monkeypatch):
    @asynccontextmanager
    async def broken():
        raise RuntimeError("postgresql://user:secret@host/db api_key=secret")
        yield
    monkeypatch.setattr(api, "open_knowledge_runtime", broken)
    with TestClient(app_for("admin")) as client:
        response = client.post("/api/v1/knowledge/sources", json={"doc_id": "d", "source_uri": "urn:d"})
    assert response.status_code == 503
    assert "secret" not in response.text and "postgresql" not in response.text


def test_source_citations_preserve_literal_table_ranges_and_stable_sha():
    text = "# 保修\r\n\r\n仅限家庭使用。\r\n\r\n| 型号 | 年限 |\r\n| --- | --- |\r\n| A | 3年 |\r\n"
    version = document_fingerprint(text)
    spans = _original_evidence(text, doc_id="doc", source_id="src", version_id=version)
    table = spans[-1]
    assert "| A | 3年 |\r\n" in table.content
    assert "仅限家庭使用。" in table.content
    assert "型号：A" not in table.content
    assert table.doc_version == version
    assert table.locator.start_line == 3
    assert table.locator.source == "src"
    assert table.span_id == _original_evidence(text, doc_id="doc", source_id="src", version_id=version)[-1].span_id


def test_upload_schema_rejects_paths_extra_fields_and_nontext(monkeypatch):
    class Runtime:
        config = config()
        async def upload(self, *args, **kwargs):
            pytest.fail("invalid upload reached persistence")
    @asynccontextmanager
    async def opened():
        yield Runtime()
    monkeypatch.setattr(api, "open_knowledge_runtime", opened)
    with TestClient(app_for("admin")) as client:
        for media in ("application/pdf", "application/octet-stream", "text/plain;charset=gbk"):
            response = client.post("/api/v1/knowledge/sources/src/versions", content=b"hello", headers={"Content-Type": media})
            assert response.status_code == 415
        assert client.post("/api/v1/knowledge/sources/src/versions", content=b"x" * 1001,
                           headers={"Content-Type": "text/markdown;charset=utf-8"}).status_code == 413
        assert client.post("/api/v1/knowledge/sources", json={"doc_id": "../file", "source_uri": "urn:d"}).status_code == 422
        assert client.post("/api/v1/knowledge/sources", json={"doc_id": "doc", "source_uri": "urn:d", "role": "admin"}).status_code == 422


def test_answer_without_explicit_credentials_never_embeds_or_calls_model():
    class Forbidden:
        def __getattr__(self, name):
            pytest.fail(f"unexpected network/storage call {name}")
    runtime = KnowledgeRuntime(Forbidden(), config(knowledge_api_key=None), embedder=Forbidden())
    answer = asyncio.run(runtime.answer("质保多久"))
    assert answer.status == "unavailable" and answer.reason == "model_failure"


@pytest.mark.parametrize("content", [b"\xff", b"hello\x00world", b"\x01binary", b"   ", b"x" * 1001])
def test_upload_rejects_invalid_utf8_binary_empty_or_oversize_before_storage(content):
    class Forbidden:
        def __getattr__(self, name):
            pytest.fail(f"invalid upload reached storage: {name}")
    runtime = KnowledgeRuntime(Forbidden(), config())
    with pytest.raises(ValueError):
        asyncio.run(runtime.upload("src", content, title="test"))


def test_open_runtime_does_not_fallback_to_business_dsn():
    async def exercise():
        with pytest.raises(KnowledgeUnavailable):
            async with open_knowledge_runtime(config(knowledge_database_url=None, database_url="postgresql://must-not-connect")):
                pytest.fail("missing knowledge DSN opened a connection")
    asyncio.run(exercise())


def test_revision_check_uses_actual_served_digest_and_timeout(monkeypatch):
    original_client = httpx.AsyncClient
    async def tags(request):
        return httpx.Response(200, json={"models": [{"name": "bge-m3:latest", "digest": "sha256:" + "b" * 64}]})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(tags), **kwargs))
    with pytest.raises(KnowledgeUnavailable):
        asyncio.run(RevisionEmbeddingClient(config()).embed(["text"]))


def test_query_manifest_mismatch_happens_before_embedding():
    class Storage:
        async def pin_active_release(self):
            return {"release_id": "r", "embedding_model": "bge-m3", "embedding_revision": "wrong",
                    "embedding_dim": 3, "embedding_normalized": True, "expected_chunks": 1,
                    "corpus_sha256": "a" * 64, "bm25_sha256": "b" * 64, "distance_metric": "cosine"}
    class Embedder:
        async def embed(self, texts):
            pytest.fail("manifest mismatch must stop before embedding")
    with pytest.raises(KnowledgeUnavailable):
        asyncio.run(KnowledgeRuntime(Storage(), config(), embedder=Embedder()).search("2024款凯美瑞保修"))


@pytest.mark.skipif(not os.environ.get("TEST_KNOWLEDGE_DATABASE_URL"),
                    reason="disposable PostgreSQL/pgvector not explicitly configured")
def test_real_api_worker_build_publish_search_cite_and_revoke(monkeypatch):
    import psycopg

    async def exercise():
        dsn = os.environ["TEST_KNOWLEDGE_DATABASE_URL"]
        cfg = config(knowledge_database_url=dsn)
        # Only the embedding boundary is replaced. All repositories, SQL, job
        # leases, transitions, runtime and HTTP schemas run for real.
        class Embedder:
            async def embed(self, texts):
                return [[1.0, 0.0, 0.0] for _ in texts]
        @asynccontextmanager
        async def opened():
            async with open_knowledge_runtime(cfg) as runtime:
                runtime.embedder = Embedder()
                yield runtime
        monkeypatch.setattr(api, "open_knowledge_runtime", opened)
        async with await psycopg.AsyncConnection.connect(dsn, autocommit=True, connect_timeout=10) as connection:
            cursor = await connection.execute("SELECT 1 FROM pg_namespace WHERE nspname='knowledge'")
            if await cursor.fetchone():
                pytest.fail("requires empty disposable database; refusing existing knowledge schema")
            owned = False
            try:
                path = Path(__file__).resolve().parents[1] / "scripts" / "migrate_knowledge.py"
                spec = importlib.util.spec_from_file_location("knowledge_api_migration", path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                await module.migrate(connection)
                owned = True
                app = app_for("admin")
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    prefix = "/api/v1/knowledge"
                    response = await client.post(prefix + "/sources", json={"doc_id": "warranty", "source_uri": "file:///private/source.md"})
                    assert response.status_code == 201, response.text
                    source = response.json()["source_id"]
                    # API has no metadata parameter yet (owned by main agent).
                    # Use the same runtime upload with canonical scope metadata.
                    async with opened() as runtime:
                        uploaded = await runtime.upload(source, "# 保修\n\n家庭使用保修3年。\n".encode(),
                            title="保修", metadata={"vehicle_scopes": [{"model": "CAMRY", "year": 2024}]})
                    version = uploaded["version_id"]
                    queued = await client.post(prefix + "/builds", json={"version_ids": [version], "idempotency_key": "first-build"})
                    assert queued.status_code == 202, queued.text
                    job_id = queued.json()["job_id"]
                    async with opened() as runtime:
                        assert await runtime.run_one_job("test-worker")
                        assert await runtime.storage.pin_active_release() is None
                    state = await client.get(prefix + "/builds/" + job_id)
                    assert state.json()["status"] == "succeeded", state.text
                    assert state.json()["release_status"] == "ready", state.text
                    release = state.json()["release_id"]
                    assert (await client.post(prefix + f"/releases/{release}/publish")).status_code == 200
                    app.dependency_overrides[get_current_user] = lambda: {"user_id": 8, "role": "sales"}
                    search = await client.get(prefix + "/search", params={"q": "2024款凯美瑞保修"})
                    assert search.status_code == 200, search.text
                    citation = search.json()["hits"][0]["citation"]
                    assert set(citation) == {"citation_id", "span_id", "source_id", "document_version", "title", "locator", "quote", "url"}
                    assert citation["document_version"] == version
                    assert citation["quote"] == "家庭使用保修3年。\n"
                    assert "private" not in str(citation)
                    assert (await client.get(citation["url"])).json() == citation
                    app.dependency_overrides[get_current_user] = lambda: {"user_id": 7, "role": "admin"}
                    revoked = await client.post(prefix + f"/sources/{source}/revoke", json={"reason": "withdrawn"})
                    assert revoked.status_code == 200
                    assert (await client.get(citation["url"])).status_code == 404
                    assert (await client.get(prefix + "/search", params={"q": "2024款凯美瑞保修"})).json()["hits"] == []
            finally:
                if owned:
                    await connection.execute("DROP SCHEMA knowledge CASCADE")
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(exercise())
    else:
        asyncio.run(exercise())


def test_answer_bundle_preserves_release_and_frozen_citation_schema(monkeypatch):
    from app.services.knowledge.evidence import Citation, GroundedAnswer
    from app.services.knowledge.retrieval import RetrievalResult
    from app.services.knowledge.domain import ScoredEvidence

    evidence = _original_evidence("保修3年。\n", doc_id="doc", source_id="src",
                                  version_id=document_fingerprint("保修3年。\n"))[0]
    calls = []
    class Runtime(KnowledgeRuntime):
        async def search(self, query, *, top_k=5, query_plan=None):
            calls.append("search")
            scored = (ScoredEvidence(evidence, 0.1),)
            return RetrievalResult("rel", scored, scored, ("embedding_unavailable",))
        async def _answer_result(self, query, result):
            calls.append("answer")
            quote = Citation("cite-id", evidence.span_id, evidence.doc_id, evidence.doc_version,
                             evidence.locator, evidence.content)
            return GroundedAnswer("ok", "来源原文引述", (evidence.content,), (evidence.span_id,), (quote,))
        async def citation(self, release_id, span_id):
            return {"source_id": "src", "version_id": evidence.doc_version, "title": "保修",
                    "locator": asdict(evidence.locator)}
    runtime = Runtime(None, config(knowledge_api_key="test-key", knowledge_budget_cny=50,
                                  knowledge_input_per_million_cny=1, knowledge_output_per_million_cny=2))
    bundle = asyncio.run(runtime.answer_bundle("2024款凯美瑞保修多久"))
    assert calls == ["search", "answer"]
    assert bundle["knowledge_release_id"] == "rel"
    assert bundle["answer_status"] == "partial"
    assert bundle["data_as_of"] is None
    assert bundle["limitations"] == ["原文摘录模式。", "仅核对引用与来源原文是否一致，回答适用性仍需结合版本条件。",
                                      "向量检索暂不可用，本次使用关键词检索。"]
    assert set(bundle["citations"][0]) == {"citation_id", "span_id", "source_id", "document_version", "title", "locator", "quote", "url"}


def test_scope_plan_clarification_and_metadata_matching():
    from app.services.knowledge.query import plan_query
    from app.services.knowledge.runtime import (
        QueryClarification, _matches_scope, _validated_metadata,
    )

    def scope(model, year=None, power=None):
        return {"vehicle_scopes": [{"model": model, "year": year, "powertrain": power}]}

    camry = plan_query("2024款凯美瑞2.5双擎保修").entities
    assert _matches_scope(scope("CAMRY", 2024, "2.5 双擎"), camry)
    assert not _matches_scope(scope("CAMRY", 2024, "2.5 燃油"), camry)
    assert not _matches_scope(scope("CAMRY", None, "2.5 双擎"), camry)  # unknown year is not a wildcard
    assert not _matches_scope(scope("HIGHLANDER", 2024), camry)
    assert _matches_scope(scope("CAMRY", 2024), plan_query("2024款凯美瑞保修").entities)
    assert not _matches_scope({}, plan_query("2024款凯美瑞保修").entities)
    assert _matches_scope({}, ())  # no model scope -> explicit generic plan never reaches here
    for bad in ({"vehicle_scopes": [{"model": "camry"}]},
                {"vehicle_scopes": [{"model": "CAMRY", "year": True}]},
                {"vehicle_scopes": [{"model": "CAMRY", "powertrain": "2.0T"}]},
                {"vehicle_scopes": [{"model": "CAMRY", "tenant": "x"}]}):
        with pytest.raises(ValueError):
            _validated_metadata(bad)
    assert _validated_metadata({"vehicle_scopes": [{"model": "RAV4", "year": 2025,
                                                   "powertrain": "2.0 燃油"}]})["vehicle_scopes"]


def test_clarification_never_touches_storage_embedding_or_model():
    from app.services.knowledge.runtime import QueryClarification
    class Forbidden:
        def __getattr__(self, name):
            pytest.fail(f"clarification touched {name}")
    runtime = KnowledgeRuntime(Forbidden(), config(knowledge_api_key="key", knowledge_budget_cny=50,
        knowledge_input_per_million_cny=1, knowledge_output_per_million_cny=2), embedder=Forbidden())
    bundle = asyncio.run(runtime.answer_bundle("这车保修多久"))
    assert bundle["answer_status"] == "clarification"
    assert "车型" in bundle["reply"] and bundle["data_as_of"] is None
    with pytest.raises(QueryClarification):
        asyncio.run(runtime.search("这车保修多久"))


def test_bundle_plans_once_and_uses_same_scoped_source_ids_for_bm25_and_dense():
    from hashlib import sha256
    from app.services.knowledge.runtime import _artifact
    from app.services.knowledge.query import plan_query

    def row(model, text, source):
        evidence = _original_evidence(text + "\n", doc_id=source, source_id=source,
                                      version_id=document_fingerprint(text + "\n"))[0]
        return evidence, {"release_id": "rel", "chunk_id": evidence.span_id, "span_id": evidence.span_id,
            "version_id": evidence.doc_version, "original_text": evidence.content, "content": evidence.content,
            "section_path": [], "locator": asdict(evidence.locator), "source_id": source,
            "metadata": {"vehicle_scopes": [{"model": model, "year": 2024}]}}

    camry, camry_row = row("CAMRY", "凯美瑞保修3年", "src-camry")
    high, high_row = row("HIGHLANDER", "汉兰达保修2年", "src-high")
    artifact = _artifact([{"chunk_id": r["chunk_id"], "span_id": r["span_id"], "content": r["content"]}
                          for r in (camry_row, high_row)])
    class Store:
        dense_sources = None
        async def pin_active_release(self):
            return {"release_id": "rel", "embedding_model": "model", "embedding_revision": "revision",
                    "embedding_dim": 2, "embedding_normalized": True, "expected_chunks": 2,
                    "corpus_sha256": "a" * 64, "bm25_sha256": sha256(artifact).hexdigest(),
                    "distance_metric": "cosine", "evaluation": {"bm25_artifact": artifact.decode()}}
        async def list_evidence(self, release_id):
            return [camry_row, high_row]
        async def _one(self, sql, params):
            return {"doc_id": params[0]}
        async def get_citation(self, release_id, span_id):
            return camry_row if span_id == camry.span_id else high_row
        async def search_dense(self, release_id, vector, *, source_ids=None, **kwargs):
            self.dense_sources = source_ids
            return [camry_row, high_row]
    class Embedder:
        async def embed(self, texts):
            return [[1, 0]]
    store = Store()
    runtime = KnowledgeRuntime(store, config(knowledge_embedding_model="model",
        knowledge_embedding_revision="revision", knowledge_embedding_dimension=2), embedder=Embedder())
    result = asyncio.run(runtime.search("2024款凯美瑞保修", query_plan=plan_query("2024款凯美瑞保修")))
    assert [item.evidence.doc_id for item in result.ranked] == ["src-camry"]
    assert store.dense_sources == ["src-camry"]
    assert "凯美瑞" in result.ranked[0].evidence.content


def test_embedding_timeout_returns_explicit_scoped_bm25_degradation():
    from app.services.knowledge.runtime import _artifact
    from hashlib import sha256
    evidence = _original_evidence("保修3年。\n", doc_id="doc", source_id="src",
                                  version_id=document_fingerprint("保修3年。\n"))[0]
    chunk = {"chunk_id": evidence.span_id, "span_id": evidence.span_id, "content": evidence.content}
    artifact = _artifact([chunk])
    row = dict(chunk, version_id=evidence.doc_version, original_text=evidence.content,
               section_path=[], locator=asdict(evidence.locator), source_id="src", release_id="rel",
               metadata={"vehicle_scopes": [{"model": "CAMRY", "year": 2024}]})
    class Storage:
        async def pin_active_release(self):
            return {"release_id": "rel", "embedding_model": "bge-m3", "embedding_revision": REVISION,
                    "embedding_dim": 3, "embedding_normalized": True, "expected_chunks": 1,
                    "corpus_sha256": "a" * 64, "bm25_sha256": sha256(artifact).hexdigest(),
                    "distance_metric": "cosine", "evaluation": {"bm25_artifact": artifact.decode()}}
        async def list_evidence(self, release_id):
            return [row]
        async def _one(self, sql, params):
            return {"doc_id": "doc"}
        async def get_citation(self, release_id, span_id):
            return row
        async def search_dense(self, *args, **kwargs):
            pytest.fail("timeout must not issue a dense search")
    class Embedder:
        async def embed(self, texts):
            raise httpx.ReadTimeout("sensitive provider details")
    result = asyncio.run(KnowledgeRuntime(Storage(), config(), embedder=Embedder()).search("2024款凯美瑞保修"))
    assert result.degraded == ("embedding_unavailable",)
    assert result.ranked[0].evidence == evidence
