"""Hybrid ranking of an explicitly scoped immutable knowledge snapshot."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol, Sequence

from app.services.knowledge.domain import Evidence, ScoredEvidence
from app.services.knowledge.ranking import BM25Index, ChineseTokenizer, dense_search, reciprocal_rank_fusion


class QueryEmbedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class Reranker(Protocol):
    async def rank(self, query: str, candidates: Sequence[ScoredEvidence]) -> Sequence[ScoredEvidence]: ...


async def rerank_candidates(query: str, candidates: Sequence[ScoredEvidence], *,
                            reranker: Reranker, timeout: float) -> tuple[ScoredEvidence, ...]:
    """Accept only a permutation of original records; retain original RRF scores."""
    async with asyncio.timeout(timeout):
        reranked = tuple(await reranker.rank(query, candidates))
    expected = {item.evidence.span_id: item for item in candidates}
    if len(reranked) != len(candidates) or len({item.evidence.span_id for item in reranked}) != len(candidates):
        raise ValueError("reranker must return a permutation of candidates")
    if any(item.evidence.span_id not in expected or item.evidence != expected[item.evidence.span_id].evidence
           for item in reranked):
        raise ValueError("reranker changed candidate evidence")
    return tuple(expected[item.evidence.span_id] for item in reranked)


@dataclass(frozen=True)
class KnowledgeSnapshot:
    release_id: str
    model: str
    dimension: int
    evidence: tuple[Evidence, ...]
    vectors: tuple[tuple[float, ...], ...]

    def __post_init__(self):
        if not self.release_id or not self.model or not 1 <= self.dimension <= 16000:
            raise ValueError("snapshot requires release/model/dimension")
        if len(self.evidence) != len(self.vectors) or any(len(v) != self.dimension for v in self.vectors):
            raise ValueError("snapshot evidence and vector dimensions do not match")
        if len({e.span_id for e in self.evidence}) != len(self.evidence):
            raise ValueError("snapshot evidence IDs must be unique")


@dataclass(frozen=True)
class RetrievalResult:
    release_id: str
    candidates: tuple[ScoredEvidence, ...]
    ranked: tuple[ScoredEvidence, ...]
    degraded: tuple[str, ...] = ()


class HybridRetriever:
    """The caller MUST load a server-authorized, active, non-revoked snapshot.

    Final revalidation is mandatory: ranking is not an authorization boundary.
    No process-global corpus or client-supplied ACL filters are accepted here.
    """
    def __init__(self, *, embedder: QueryEmbedder, embedding_model: str,
                 tokenizer: ChineseTokenizer | None = None, reranker: Reranker | None = None,
                 embedding_timeout: float = 0.4, rerank_timeout: float = 0.3):
        if embedding_timeout <= 0 or rerank_timeout <= 0:
            raise ValueError("retrieval timeouts must be positive")
        self.embedder = embedder
        self.embedding_model = embedding_model
        self.tokenizer = tokenizer or ChineseTokenizer()
        self.reranker = reranker
        self.embedding_timeout = embedding_timeout
        self.rerank_timeout = rerank_timeout

    async def search(self, query: str, snapshot: KnowledgeSnapshot, *, top_k: int = 5,
                     use_reranker: bool = False,
                     revalidate: Callable[[tuple[str, ...]], Awaitable[set[str]]]) -> RetrievalResult:
        if not isinstance(query, str) or not query.strip() or len(query) > 10000:
            raise ValueError("query must be nonempty and bounded")
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        if snapshot.model != self.embedding_model:
            raise ValueError("query and release embedding models must match")
        degraded: list[str] = []
        # CPU work runs outside the event loop. At current scope this is rebuilt
        # from an authorized snapshot; version-scoped caching can follow profiling.
        sparse_task = asyncio.to_thread(
            lambda: BM25Index(snapshot.evidence, tokenizer=self.tokenizer).search(query, top_k=20)
        )

        async def semantic():
            try:
                async with asyncio.timeout(self.embedding_timeout):
                    vectors = await self.embedder.embed([query])
                    if len(vectors) != 1 or len(vectors[0]) != snapshot.dimension:
                        raise ValueError("query vector dimension mismatch")
                    return await asyncio.to_thread(dense_search, vectors[0], snapshot.evidence,
                                                   snapshot.vectors, top_k=20)
            except (TimeoutError, OSError, RuntimeError, ValueError):
                degraded.append("embedding_unavailable")
                return ()

        sparse, dense = await asyncio.gather(sparse_task, semantic())
        candidates = reciprocal_rank_fusion((sparse, dense), top_k=20)
        ranked = candidates
        if use_reranker and self.reranker and candidates:
            try:
                ranked = await rerank_candidates(query, candidates, reranker=self.reranker,
                                                  timeout=self.rerank_timeout)
            except Exception:
                degraded.append("reranker_unavailable")
        allowed = await revalidate(tuple(item.evidence.span_id for item in candidates))
        candidates = tuple(item for item in candidates if item.evidence.span_id in allowed)
        ranked = tuple(item for item in ranked if item.evidence.span_id in allowed)[:top_k]
        return RetrievalResult(snapshot.release_id, candidates, ranked, tuple(degraded))
