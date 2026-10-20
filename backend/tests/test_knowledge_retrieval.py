import asyncio

import pytest

from app.services.knowledge.domain import Evidence, SourceLocator, ScoredEvidence, document_fingerprint
from app.services.knowledge.retrieval import HybridRetriever, KnowledgeSnapshot


def snapshot():
    evidence = tuple(Evidence(doc_id=name, doc_version=document_fingerprint(name), content=content,
                              section_path=(), locator=SourceLocator(name, 1, 1))
                     for name, content in [('a', '测试车型 RAV4 配置'), ('b', '测试车型 通勤用途')])
    return KnowledgeSnapshot('release', 'embedding', 2, evidence, ((1., 0.), (0., 1.)))


class Embedder:
    async def embed(self, texts):
        return [[1., 0.]]


async def allow_all(ids):
    return set(ids)


def test_hybrid_preserves_release_and_filters_revoked_before_return():
    data = snapshot()
    async def allow(ids):
        return {data.evidence[1].span_id}
    result = asyncio.run(HybridRetriever(embedder=Embedder(), embedding_model='embedding').search(
        'RAV4', data, revalidate=allow))
    assert result.release_id == 'release'
    assert all(item.evidence.span_id != data.evidence[0].span_id for item in result.candidates)


def test_embedding_outage_uses_keyword_result():
    class Offline:
        async def embed(self, texts):
            raise RuntimeError('offline')
    result = asyncio.run(HybridRetriever(embedder=Offline(), embedding_model='embedding').search(
        'RAV4', snapshot(), revalidate=allow_all))
    assert len(result.ranked) == 1
    assert result.ranked[0].evidence.doc_id == 'a'
    assert result.degraded == ('embedding_unavailable',)


def test_reranker_cannot_introduce_new_evidence():
    class InvalidRanker:
        async def rank(self, query, candidates):
            return []
    result = asyncio.run(HybridRetriever(embedder=Embedder(), embedding_model='embedding',
                                         reranker=InvalidRanker()).search(
        'RAV4', snapshot(), use_reranker=True, revalidate=allow_all))
    assert result.ranked
    assert 'reranker_unavailable' in result.degraded


def test_embedding_model_mismatch_fails_before_retrieval():
    with pytest.raises(ValueError):
        asyncio.run(HybridRetriever(embedder=Embedder(), embedding_model='other').search(
            'RAV4', snapshot(), revalidate=allow_all))
