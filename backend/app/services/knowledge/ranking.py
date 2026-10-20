"""Local retrieval primitives, with no model, DB, numpy or jieba dependency.

SECURITY CONTRACT: every corpus/ranking passed here MUST already be restricted
by the caller to authorized sources, document versions, release, validity and
revocation state. BM25 statistics must be built from that scoped corpus, not a
global index followed by top-k filtering. These functions do not enforce ACLs.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
import math
import re

from app.services.knowledge.domain import Evidence, ScoredEvidence

# Deliberately a deterministic bigram tokenizer, NOT a linguistic segmenter.
_LEXEME = re.compile(
    r"[a-z0-9]+(?:[-_.+/][a-z0-9]+)*|"
    r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0002fa1f]+"
)
_ASCII_MODEL_CHAR = re.compile(r"[a-z0-9_.+/\-]")


class ChineseTokenizer:
    """Case-folded whole ASCII model tokens + overlapping Chinese bigrams.

    A one-character Chinese run is retained as a unigram. ``aliases`` maps an
    alias to its canonical spelling (e.g. a project-maintained model dictionary).
    Longest aliases win, replacement is single-pass and ASCII aliases match only
    complete model tokens. Use the same tokenizer for indexing and querying.
    """

    def __init__(self, aliases: Mapping[str, str] | None = None) -> None:
        normalized: dict[str, str] = {}
        for alias, canonical in (aliases or {}).items():
            if not isinstance(alias, str) or not isinstance(canonical, str):
                raise TypeError("aliases and canonical spellings must be strings")
            alias, canonical = alias.strip().casefold(), canonical.strip().casefold()
            if not alias or not canonical or not _LEXEME.search(canonical):
                raise ValueError("aliases and canonical spellings must contain tokens")
            if alias in normalized and normalized[alias] != canonical:
                raise ValueError("case-folded aliases must not conflict")
            normalized[alias] = canonical
        self._aliases = normalized
        patterns: list[str] = []
        for alias in sorted(normalized, key=lambda item: (-len(item), item)):
            left = r"(?<![a-z0-9_.+/\-])" if _ASCII_MODEL_CHAR.fullmatch(alias[0]) else ""
            right = r"(?![a-z0-9_.+/\-])" if _ASCII_MODEL_CHAR.fullmatch(alias[-1]) else ""
            patterns.append(left + re.escape(alias) + right)
        self._pattern = re.compile("|".join(patterns)) if patterns else None

    def __call__(self, text: str) -> tuple[str, ...]:
        normalized = text.casefold()
        if self._pattern:
            normalized = self._pattern.sub(lambda match: " " + self._aliases[match.group()] + " ", normalized)
        tokens: list[str] = []
        for match in _LEXEME.finditer(normalized):
            word = match.group()
            if word[0].isascii() or len(word) == 1:
                tokens.append(word)
            else:
                tokens.extend(word[i:i + 2] for i in range(len(word) - 1))
        return tuple(tokens)


def _check_top_k(top_k: int) -> None:
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 0:
        raise ValueError("top_k must be a non-negative integer")


def _unique_corpus(corpus: Iterable[Evidence]) -> tuple[Evidence, ...]:
    documents = tuple(corpus)
    if len({document.span_id for document in documents}) != len(documents):
        raise ValueError("corpus contains duplicate span IDs")
    return documents


class BM25Index:
    """Okapi BM25 on a caller-scoped immutable evidence snapshot.

    For each distinct query term t:
      IDF(t) = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))
      score += IDF(t) * tf(t,d)*(k1+1) /
               (tf(t,d) + k1*(1-b+b*len(d)/avgdl))
    Query terms are scored once; unknown terms contribute zero.
    """

    def __init__(
        self, corpus: Iterable[Evidence], *, tokenizer: ChineseTokenizer | None = None,
        k1: float = 1.5, b: float = 0.75,
    ) -> None:
        if not math.isfinite(k1) or k1 <= 0 or not math.isfinite(b) or not 0 <= b <= 1:
            raise ValueError("k1 must be positive and finite; b must be between 0 and 1")
        self.corpus = _unique_corpus(corpus)
        self.tokenizer = tokenizer if tokenizer is not None else ChineseTokenizer()
        self.k1, self.b = k1, b
        self._lengths: list[int] = []
        self._postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for index, evidence in enumerate(self.corpus):
            counts = Counter(self.tokenizer(evidence.content))
            self._lengths.append(sum(counts.values()))
            for token, frequency in counts.items():
                self._postings[token].append((index, frequency))
        self._avgdl = sum(self._lengths) / len(self.corpus) if self.corpus else 0.0

    def search(self, query: str, *, top_k: int = 10) -> tuple[ScoredEvidence, ...]:
        """Return matching evidence only; empty/no-signal queries return ()."""
        _check_top_k(top_k)
        terms = set(self.tokenizer(query))
        if not terms or not self._avgdl or not top_k:
            return ()
        scores: dict[int, float] = defaultdict(float)
        for term in sorted(terms):
            postings = self._postings.get(term, ())
            if not postings:
                continue
            idf = math.log1p((len(self.corpus) - len(postings) + 0.5) / (len(postings) + 0.5))
            for index, frequency in postings:
                denominator = frequency + self.k1 * (1 - self.b + self.b * self._lengths[index] / self._avgdl)
                scores[index] += idf * frequency * (self.k1 + 1) / denominator
        ranked = sorted(scores, key=lambda index: (-scores[index], self.corpus[index].span_id))[:top_k]
        return tuple(ScoredEvidence(self.corpus[index], scores[index]) for index in ranked)


def reciprocal_rank_fusion(
    rankings: Iterable[Iterable[Evidence | ScoredEvidence]], *, k: float = 60.0, top_k: int = 10,
) -> tuple[ScoredEvidence, ...]:
    """RRF = sum_routes 1/(k + unique_rank), with ranks starting at 1.

    A stable span ID contributes at most once per route; later duplicates do not
    consume a rank. Distinct routes can each contribute once for the same ID.
    Input scores are ignored; ties are broken lexicographically by span ID.
    """
    _check_top_k(top_k)
    if not math.isfinite(k) or k < 0:
        raise ValueError("RRF k must be non-negative and finite")
    contributions: dict[str, list[float]] = defaultdict(list)
    evidence_by_id: dict[str, Evidence] = {}
    for ranking in rankings:
        seen: set[str] = set()
        for item in ranking:
            evidence = item.evidence if isinstance(item, ScoredEvidence) else item
            if evidence.span_id in seen:
                continue
            seen.add(evidence.span_id)
            evidence_by_id.setdefault(evidence.span_id, evidence)
            contributions[evidence.span_id].append(1.0 / (k + len(seen)))
    scores = {span_id: math.fsum(values) for span_id, values in contributions.items()}
    ids = sorted(scores, key=lambda span_id: (-scores[span_id], span_id))[:top_k]
    return tuple(ScoredEvidence(evidence_by_id[span_id], scores[span_id]) for span_id in ids)


def _vector(values: Sequence[float]) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if any(not math.isfinite(value) for value in result):
        raise ValueError("vectors must contain finite numbers")
    return result


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Pure cosine similarity; equal empty/zero vectors yield 0, mismatch raises.

    Rescale before taking norms to avoid overflow/underflow on finite vectors.
    """
    a, b = _vector(left), _vector(right)
    if len(a) != len(b):
        raise ValueError("vector dimensions must match")
    a_scale, b_scale = max(map(abs, a), default=0.0), max(map(abs, b), default=0.0)
    if not a_scale or not b_scale:
        return 0.0
    a, b = tuple(x / a_scale for x in a), tuple(x / b_scale for x in b)
    similarity = math.fsum(x * y for x, y in zip(a, b)) / (
        math.sqrt(math.fsum(x * x for x in a)) * math.sqrt(math.fsum(y * y for y in b))
    )
    return max(-1.0, min(1.0, similarity))


def dense_search(
    query_vector: Sequence[float], corpus: Iterable[Evidence], vectors: Sequence[Sequence[float]],
    *, top_k: int = 10,
) -> tuple[ScoredEvidence, ...]:
    """Exact cosine ranking of caller-filtered evidence/vector pairs, no embedding.

    Zero/empty query vectors return no candidates. All supplied vectors are
    validated even when the query has no signal or top_k is zero.
    """
    _check_top_k(top_k)
    documents = _unique_corpus(corpus)
    query = _vector(query_vector)
    if len(documents) != len(vectors):
        raise ValueError("one vector is required per evidence span")
    candidates: list[ScoredEvidence] = []
    for document, vector in zip(documents, vectors):
        candidates.append(ScoredEvidence(document, cosine_similarity(query, vector)))
    if not any(query):
        return ()
    return tuple(sorted(candidates, key=lambda item: (-item.score, item.evidence.span_id))[:top_k])
