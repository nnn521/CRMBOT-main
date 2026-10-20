"""Optional local cross-encoder via Hugging Face Text Embeddings Inference.

Real protocol, not Ollama generation/embedding masquerading as reranking:
https://huggingface.co/docs/text-embeddings-inference/quick_tour#re-rankers
https://github.com/huggingface/text-embeddings-inference/blob/main/docs/openapi.json

TEI GET /info identifies model_id and model_type.reranker. POST /rerank takes
query/texts/raw_scores/return_text/truncate and returns [{index, score}]. No model
is installed, downloaded or started here. Scores only determine order; returned
ScoredEvidence objects retain original evidence AND RRF scores.
"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence
import ipaddress
import json
import math
import re
from urllib.parse import urlsplit

import httpx

from app.services.knowledge.domain import ScoredEvidence


MAX_INPUT_BYTES = 64000
_COMPLEX_QUERY = re.compile(r"比较|对比|区别|同时|并且|条件|除外|是否|但是|分别|compare|versus|\bvs\b", re.I)


def should_rerank(query: str, candidates: Sequence[ScoredEvidence], *, top_k: int,
                  min_candidates: int = 4, max_relative_gap: float = 0.15) -> bool:
    """Deterministic latency gate, not a claim that RRF scores are calibrated.

    Reorder only when there are alternatives beyond the returned top_k, enough
    candidates, and either close first/second RRF ranks or a comparison/condition
    question. Large original spans are skipped rather than silently truncated.
    """
    if (not isinstance(query, str) or not query.strip() or len(query) > 2000
            or not max(min_candidates, top_k + 1) <= len(candidates) <= 20):
        return False
    if len(query.encode("utf-8")) + sum(len(c.evidence.content.encode("utf-8")) for c in candidates) > MAX_INPUT_BYTES:
        return False
    first, second = candidates[0].score, candidates[1].score
    gap = (first - second) / max(abs(first), 1e-12)
    return bool(_COMPLEX_QUERY.search(query)) or 0 <= gap <= max_relative_gap


class TEIReranker:
    """Loopback-only TEI reranker implementing retrieval.Reranker.rank.

    Both info verification and inference share one total deadline (<=300ms).
    Redirects/proxy environment are disabled; no data is sent to an arbitrary
    remote endpoint. Missing/wrong model, truncation, partial/duplicate/unknown
    indices and malformed/nonfinite scores fail and are degraded by the caller.
    """

    def __init__(self, *, base_url: str, model: str, timeout: float = 0.3,
                 transport: httpx.AsyncBaseTransport | None = None):
        parsed = urlsplit(base_url)
        try:
            local = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            local = False
        if (parsed.scheme not in {"http", "https"} or not local or parsed.username or parsed.password
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            raise ValueError("reranker URL must be a loopback HTTP(S) origin")
        if not isinstance(model, str) or not model.strip() or not 0 < timeout <= 0.3:
            raise ValueError("reranker requires a model ID and timeout <=300ms")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.transport = transport

    async def _json(self, client: httpx.AsyncClient, method: str, path: str, **kwargs):
        async with client.stream(method, self.base_url + path, **kwargs) as response:
            if response.status_code != 200:
                raise RuntimeError("local reranker unavailable")
            content = bytearray()
            async for block in response.aiter_bytes():
                content.extend(block)
                if len(content) > 65536:
                    raise ValueError("reranker response exceeds limit")
        return json.loads(content)

    async def rank(self, query: str, candidates: Sequence[ScoredEvidence]) -> tuple[ScoredEvidence, ...]:
        if not isinstance(query, str) or not query.strip() or len(query) > 2000 or not 1 <= len(candidates) <= 20:
            raise ValueError("reranker requires query <=2000 characters and 1-20 candidates")
        if len({c.evidence.span_id for c in candidates}) != len(candidates):
            raise ValueError("reranker candidates must be distinct")
        if len(query.encode("utf-8")) + sum(len(c.evidence.content.encode("utf-8")) for c in candidates) > MAX_INPUT_BYTES:
            raise ValueError("reranker input exceeds limit")
        async with asyncio.timeout(self.timeout):
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport,
                                         follow_redirects=False, trust_env=False) as client:
                info = await self._json(client, "GET", "/info")
                if (not isinstance(info, dict) or info.get("model_id") != self.model
                        or not isinstance(info.get("model_type"), dict)
                        or set(info["model_type"]) != {"reranker"}):
                    raise ValueError("configured model is not the served TEI reranker")
                rows = await self._json(client, "POST", "/rerank", json={
                    "query": query, "texts": [c.evidence.content for c in candidates],
                    "raw_scores": False, "return_text": False, "truncate": False,
                })
        if not isinstance(rows, list) or len(rows) != len(candidates):
            raise ValueError("reranker must score every candidate")
        scored = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("invalid reranker row")
            index, score = row.get("index"), row.get("score")
            if (isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(candidates)
                    or index in scored or isinstance(score, bool) or not isinstance(score, (int, float))
                    or not math.isfinite(score)):
                raise ValueError("invalid reranker index or score")
            # return_text=false; an unexpected text must still equal our original.
            if row.get("text") is not None and row["text"] != candidates[index].evidence.content:
                raise ValueError("reranker changed source text")
            scored[index] = score
        return tuple(candidates[i] for i in sorted(scored, key=lambda i: (-scored[i], i)))
