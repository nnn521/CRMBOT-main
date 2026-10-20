"""Rule-based Markdown/plain-text parsing; no model calls or filesystem access.

Each paragraph belongs to exactly one heading path. Each table row repeats its
column labels, heading path and immediately preceding paragraph in that section.
Line numbers refer to the original input, including blank lines and headings.
This is a deliberately small Markdown parser, not a CommonMark implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Literal

from app.services.knowledge.domain import Evidence, SourceLocator, document_fingerprint

_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?)|[ \t]*)$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_SEPARATOR = re.compile(r"^:?-{3,}:?$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def _cells(line: str) -> list[str]:
    """Split unescaped pipes outside inline code; preserve literal cell content."""
    text = line.strip()
    cells: list[str] = []
    cell: list[str] = []
    code_ticks = 0
    i = 0
    while i < len(text):
        char = text[i]
        if char == "\\" and i + 1 < len(text):
            # Only unescape a literal pipe; preserve other Markdown escapes.
            cell.append(text[i + 1] if text[i + 1] == "|" else text[i:i + 2])
            i += 2
            continue
        if char == "`":
            end = i + 1
            while end < len(text) and text[end] == "`":
                end += 1
            ticks = end - i
            if not code_ticks:
                code_ticks = ticks
            elif code_ticks == ticks:
                code_ticks = 0
            cell.append(text[i:end])
            i = end
            continue
        if char == "|" and not code_ticks:
            cells.append("".join(cell).strip())
            cell = []
        else:
            cell.append(char)
        i += 1
    cells.append("".join(cell).strip())
    if text.startswith("|") and cells[0] == "":
        cells.pop(0)
    if text.endswith("|") and cells and cells[-1] == "":
        cells.pop()
    return cells


def _table_header(lines: list[str], index: int) -> list[str] | None:
    if index + 1 >= len(lines) or "|" not in lines[index]:
        return None
    headers, separators = _cells(lines[index]), _cells(lines[index + 1])
    if headers and len(headers) == len(separators) and all(_SEPARATOR.fullmatch(c) for c in separators):
        return headers
    return None


def _heading(lines: list[str], index: int) -> tuple[int, str, int] | None:
    match = _ATX.match(lines[index])
    if match:
        title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2) or "").strip()
        return len(match.group(1)), title, 1
    if index + 1 < len(lines) and lines[index].strip() and "|" not in lines[index]:
        underline = _SETEXT.fullmatch(lines[index + 1])
        if underline:
            return (1 if underline.group(1).startswith("=") else 2), lines[index].strip(), 2
    return None


def _with_section(content: str, section: tuple[str, ...]) -> str:
    return f"章节：{' > '.join(section)}\n{content}" if section else content


def parse_markdown(
    text: str, *, doc_id: str, source: str, metadata: Mapping[str, object] | None = None,
) -> tuple[Evidence, ...]:
    """Parse an original Markdown string into immutable, source-addressed evidence.

    The caller supplies logical document identity and source URI. doc_version is
    the SHA-256 of the exact UTF-8 input. No ACL/version/status filtering happens
    here: callers must scope sources before building any retrieval candidates.
    """
    version = document_fingerprint(text)
    lines = text.splitlines()
    spans: list[Evidence] = []
    headings: list[tuple[int, str]] = []
    context: tuple[str, int, int] | None = None
    i = 0

    def emit(content: str, start: int, end: int, *, kind: Literal["paragraph", "table_row", "code"] = "paragraph",
             header: tuple[int, int] | None = None,
             preceding: tuple[str, int, int] | None = None) -> None:
        section = tuple(title for _, title in headings)
        spans.append(Evidence(
            doc_id=doc_id, doc_version=version, content=_with_section(content, section),
            section_path=section,
            locator=SourceLocator(
                source=source, start_line=start, end_line=end, kind=kind,
                header_start_line=header[0] if header else None,
                header_end_line=header[1] if header else None,
                context_start_line=preceding[1] if preceding else None,
                context_end_line=preceding[2] if preceding else None,
            ),
            metadata=metadata if metadata is not None else {},
        ))

    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        heading = _heading(lines, i)
        if heading:
            level, title, consumed = heading
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, title))
            context = None  # Never inherit paragraph context across a heading.
            i += consumed
            continue
        fence = _FENCE.match(lines[i])
        if fence:
            start = i
            marker = fence.group(1)
            i += 1
            closing = re.compile(r"^ {0,3}" + re.escape(marker[0]) + "{" + str(len(marker)) + r",}[ \t]*$")
            while i < len(lines):
                is_closing = closing.fullmatch(lines[i]) is not None
                i += 1
                if is_closing:
                    break
            emit("\n".join(lines[start:i]), start + 1, i, kind="code")
            context = None
            continue
        headers = _table_header(lines, i)
        if headers is not None:
            header = (i + 1, i + 2)
            preceding = context
            i += 2
            while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                if _heading(lines, i) or _FENCE.match(lines[i]) or _table_header(lines, i):
                    break
                values = _cells(lines[i])
                if len(values) > len(headers):
                    raise ValueError(f"table row at line {i + 1} has more cells than its header")
                values += [""] * (len(headers) - len(values))
                # Label every value; the first column preserves the row subject.
                row = "；".join(f"{label}：{value}" for label, value in zip(headers, values))
                if preceding:
                    row = f"表格上下文：{preceding[0]}\n{row}"
                emit(row, i + 1, i + 1, kind="table_row", header=header, preceding=preceding)
                i += 1
            context = None
            continue
        start = i
        i += 1
        while i < len(lines) and lines[i].strip():
            if _heading(lines, i) or _table_header(lines, i) or _FENCE.match(lines[i]):
                break
            i += 1
        paragraph = "\n".join(lines[start:i]).strip()
        emit(paragraph, start + 1, i)
        context = (paragraph, start + 1, i)
    return tuple(spans)


def parse_text(
    text: str, *, doc_id: str, source: str, metadata: Mapping[str, object] | None = None,
) -> tuple[Evidence, ...]:
    """Split plain text at blank lines; retain literal Markdown-like text."""
    version = document_fingerprint(text)
    lines = text.splitlines()
    spans: list[Evidence] = []
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        start = i
        while i < len(lines) and lines[i].strip():
            i += 1
        spans.append(Evidence(
            doc_id=doc_id, doc_version=version, content="\n".join(lines[start:i]).strip(),
            section_path=(), locator=SourceLocator(source, start + 1, i),
            metadata=metadata if metadata is not None else {},
        ))
    return tuple(spans)
