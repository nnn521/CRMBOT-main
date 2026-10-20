"""Immutable, dependency-free records for source evidence and retrieval scores."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import math
from types import MappingProxyType
from typing import Literal


def document_fingerprint(content: str | bytes) -> str:
    """SHA-256 of the original bytes (UTF-8 for str); do not normalize newlines."""
    return sha256(content.encode("utf-8") if isinstance(content, str) else content).hexdigest()


def _freeze(value: object) -> object:
    """Copy JSON-like metadata into recursively immutable containers."""
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("metadata keys must be strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError("metadata must contain only finite JSON-like values")


@dataclass(frozen=True, slots=True)
class SourceLocator:
    """1-based inclusive source lines; table headers/context have separate ranges."""

    source: str
    start_line: int
    end_line: int
    kind: Literal["paragraph", "table_row", "code"] = "paragraph"
    header_start_line: int | None = None
    header_end_line: int | None = None
    context_start_line: int | None = None
    context_end_line: int | None = None

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("source must not be empty")
        for start, end in (
            (self.start_line, self.end_line),
            (self.header_start_line, self.header_end_line),
            (self.context_start_line, self.context_end_line),
        ):
            if (start is None) != (end is None):
                raise ValueError("line ranges must have both endpoints")
            if start is not None and (start < 1 or end < start):
                raise ValueError("line ranges must be positive and ordered")


@dataclass(frozen=True, slots=True)
class Evidence:
    """Source identity + version + location + content determine the stable span ID.

    Metadata is copied/frozen and does not change the source span's identity.
    Content may repeat literal headings/table context, but contains no inferred facts.
    """

    doc_id: str
    doc_version: str
    content: str
    section_path: tuple[str, ...]
    locator: SourceLocator
    metadata: Mapping[str, object] = field(default_factory=dict, hash=False)
    span_id: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.doc_id or not self.content.strip():
            raise ValueError("doc_id and content must not be empty")
        if len(self.doc_version) != 64 or any(c not in "0123456789abcdef" for c in self.doc_version):
            raise ValueError("doc_version must be a lowercase SHA-256 fingerprint")
        if not isinstance(self.metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        path = tuple(self.section_path)
        if any(not isinstance(part, str) for part in path):
            raise TypeError("section_path must contain strings")
        object.__setattr__(self, "section_path", path)
        object.__setattr__(self, "metadata", _freeze(self.metadata))
        identity = json.dumps(
            {"schema": "evidence-v1", "doc_id": self.doc_id, "doc_version": self.doc_version,
             "content": self.content, "section_path": path, "locator": asdict(self.locator)},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        object.__setattr__(self, "span_id", document_fingerprint(identity))


@dataclass(frozen=True, slots=True)
class ScoredEvidence:
    """A retrieval score, not a probability or a claim of factual correctness."""

    evidence: Evidence
    score: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.score):
            raise ValueError("retrieval scores must be finite")
