"""RAG v2 primitives; independent of LLM, database and application startup.

Callers must apply authorization, release/version, validity and revocation scope
BEFORE constructing BM25Index or passing candidates to dense_search/RRF.
"""

from app.services.knowledge.domain import Evidence, ScoredEvidence, SourceLocator, document_fingerprint
from app.services.knowledge.parsing import parse_markdown, parse_text
from app.services.knowledge.ranking import (
    BM25Index,
    ChineseTokenizer,
    cosine_similarity,
    dense_search,
    reciprocal_rank_fusion,
)

__all__ = [
    "Evidence", "ScoredEvidence", "SourceLocator", "document_fingerprint",
    "parse_markdown", "parse_text", "BM25Index", "ChineseTokenizer",
    "cosine_similarity", "dense_search", "reciprocal_rank_fusion",
]
