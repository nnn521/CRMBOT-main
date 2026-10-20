"""Real TEI protocol against fake HTTP transport; no running/downloaded models."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from hashlib import sha256
import json

import httpx
import pytest

from app.core.config import Settings
from app.services.knowledge.domain import Evidence, ScoredEvidence, SourceLocator, document_fingerprint
from app.services.knowledge.reranking import TEIReranker, should_rerank
from app.services.knowledge.retrieval import rerank_candidates
from app.services.knowledge.runtime import KnowledgeRuntime, _artifact


def candidates(count=6):
    return tuple(ScoredEvidence(Evidence(str(i), document_fingerprint(str(i)), f"保修条件{i}", (),
                                        SourceLocator(f"src{i}", 1, 1)), 0.03 - i * 0.0001) for i in range(count))


def service(handler, timeout=0.3):
    return TEIReranker(base_url="http://127.0.0.1:8081", model="BAAI/bge-reranker-base",
                       timeout=timeout, transport=httpx.MockTransport(handler))


def info():
    return {"model_id": "BAAI/bge-reranker-base", "model_type": {"reranker": {"id2label": {}, "label2id": {}}}}


def test_tei_protocol_reorders_originals_and_keeps_rrf_scores():
    original = candidates()
    seen = []
    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/info":
            return httpx.Response(200, json=info())
        data = json.loads(request.content)
        assert data == {"query": "保修条件", "texts": [c.evidence.content for c in original],
                        "raw_scores": False, "return_text": False, "truncate": False}
        return httpx.Response(200, json=[{"index": i, "score": i / 10} for i in range(6)])
    result = asyncio.run(service(handler).rank("保修条件", original))
    assert seen == ["/info", "/rerank"]
    assert result == tuple(reversed(original))
    assert result[0] is original[-1]


@pytest.mark.parametrize("rows", [
    [], [{"index": 0, "score": 1}] * 6,
    [{"index": i, "score": 0.1} for i in range(5)] + [{"index": 6, "score": 0.9}],
    [{"index": i, "score": True} for i in range(6)],
    [{"index": i, "score": "0.1"} for i in range(6)],
    [{"index": i, "score": 0.1, "text": "rewritten evidence"} for i in range(6)],
    [{"index": i, "score": float("nan")} for i in range(6)],
])
def test_partial_duplicates_unknown_or_nonfinite_scores_are_rejected(rows):
    def handler(request):
        if request.url.path == "/info":
            return httpx.Response(200, json=info())
        return httpx.Response(200, content=json.dumps(rows))
    with pytest.raises(ValueError):
        asyncio.run(service(handler).rank("query", candidates()))


@pytest.mark.parametrize("payload", [
    {"model_id": "wrong", "model_type": {"reranker": {}}},
    {"model_id": "BAAI/bge-reranker-base", "model_type": {"embedding": {}}},
    {"model_id": "BAAI/bge-reranker-base", "model_type": {"classifier": {}}},
])
def test_model_info_must_identify_configured_cross_encoder(payload):
    def handler(request):
        assert request.url.path == "/info"  # never send evidence to wrong model
        return httpx.Response(200, json=payload)
    with pytest.raises(ValueError):
        asyncio.run(service(handler).rank("query", candidates()))


@pytest.mark.parametrize("url", ["http://example.com", "http://192.168.1.2:8080", "ftp://localhost",
                                  "http://user:password@127.0.0.1:8080", "http://127.0.0.1:8080/rerank"])
def test_only_local_origin_configuration_is_accepted(url):
    with pytest.raises(ValueError):
        TEIReranker(base_url=url, model="model")


def test_total_info_and_inference_deadline_is_bounded():
    async def handler(request):
        await asyncio.sleep(0.02)
        return httpx.Response(200, json=info())
    with pytest.raises(TimeoutError):
        asyncio.run(service(handler, timeout=0.005).rank("query", candidates()))
    with pytest.raises(ValueError):
        service(handler, timeout=0.301)


def test_gate_skips_trivial_clear_or_oversize_queries_and_reranks_ambiguity():
    assert should_rerank("保修条件比较", candidates(), top_k=5)
    assert should_rerank("保修", candidates(), top_k=5)  # close RRF leading ranks
    assert not should_rerank("保修", candidates(2), top_k=1)
    assert not should_rerank("保修", candidates(), top_k=6)
    assert not should_rerank("x" * 2001, candidates(), top_k=5)
    separated = (ScoredEvidence(candidates()[0].evidence, 1),) + candidates()[1:]
    assert not should_rerank("保修", separated, top_k=5)


def test_shared_reranking_validator_rejects_rewritten_and_preserves_original_scores():
    class Rewrite:
        async def rank(self, query, items):
            changed = Evidence("new", document_fingerprint("new"), "new claim", (), SourceLocator("new", 1, 1))
            return (ScoredEvidence(changed, 1),) + tuple(items[1:])
    with pytest.raises(ValueError):
        asyncio.run(rerank_candidates("query", candidates(), reranker=Rewrite(), timeout=0.3))


@pytest.mark.parametrize("mode", ["disabled", "success", "timeout", "revoked"])
def test_runtime_gate_reorder_fallback_and_fresh_revocation(mode):
    items = candidates()
    artifact = _artifact([{"chunk_id": c.evidence.span_id, "span_id": c.evidence.span_id,
                           "content": c.evidence.content} for c in items])
    rows = [{"release_id": "rel", "chunk_id": c.evidence.span_id, "span_id": c.evidence.span_id,
             "version_id": c.evidence.doc_version, "original_text": c.evidence.content,
             "content": c.evidence.content, "section_path": [], "locator": asdict(c.evidence.locator),
             "source_id": c.evidence.locator.source,
             "metadata": {"vehicle_scopes": [{"model": "CAMRY", "year": 2024}]}} for c in items]
    class Store:
        rescored = False
        async def pin_active_release(self):
            return {"release_id": "rel", "embedding_model": "model", "embedding_revision": "revision",
                    "embedding_dim": 2, "embedding_normalized": True, "expected_chunks": 6,
                    "corpus_sha256": "a" * 64, "bm25_sha256": sha256(artifact).hexdigest(),
                    "distance_metric": "cosine", "evaluation": {"bm25_artifact": artifact.decode()}}
        async def list_evidence(self, release_id):
            return rows
        async def _one(self, sql, params):
            return {"doc_id": params[0].removeprefix("src")}
        async def get_citation(self, release_id, span_id):
            if mode == "revoked" and self.rescored:
                return None
            return next(r for r in rows if r["span_id"] == span_id)
        async def search_dense(self, *args, **kwargs):
            return rows
    class Embedder:
        async def embed(self, texts):
            return [[1, 0]]
    store = Store()
    calls = []
    class Ranker:
        async def rank(self, query, candidates):
            calls.append(tuple(candidates))
            store.rescored = True
            if mode == "timeout":
                raise httpx.ReadTimeout("sensitive local detail")
            return tuple(reversed(candidates))
    cfg = Settings(_env_file=None, knowledge_embedding_model="model", knowledge_embedding_revision="revision",
                   knowledge_embedding_dimension=2, knowledge_rerank_enabled=mode != "disabled")
    result = asyncio.run(KnowledgeRuntime(store, cfg, embedder=Embedder(), reranker=Ranker()).search(
        "2024款凯美瑞保修条件比较"))
    if mode == "disabled":
        assert calls == [] and result.degraded == ()
    elif mode == "timeout":
        assert result.ranked == result.candidates[:5]
        assert result.degraded == ("reranker_unavailable",)
    elif mode == "revoked":
        assert result.ranked == result.candidates == ()
    else:
        assert result.ranked == tuple(reversed(result.candidates))[:5]
        assert result.degraded == ()
