"""Deterministic primitives using synthetic fixtures, never production facts."""

from dataclasses import FrozenInstanceError
from hashlib import sha256
import math

import pytest

from app.services.knowledge import (
    BM25Index,
    ChineseTokenizer,
    Evidence,
    ScoredEvidence,
    SourceLocator,
    cosine_similarity,
    dense_search,
    document_fingerprint,
    parse_markdown,
    parse_text,
    reciprocal_rank_fusion,
)


def evidence(text: str, *, doc_id: str = "test-document", line: int = 1) -> Evidence:
    return Evidence(
        doc_id=doc_id, doc_version=document_fingerprint(text), content=text,
        section_path=(), locator=SourceLocator("test://fixture", line, line),
    )


def test_fingerprint_hashes_original_utf8_and_bytes_without_normalizing():
    text = "测试\r\n内容"
    assert document_fingerprint(text) == sha256(text.encode("utf-8")).hexdigest()
    assert document_fingerprint(text.encode("utf-8")) == document_fingerprint(text)
    assert document_fingerprint(text) != document_fingerprint(text.replace("\r\n", "\n"))
    assert document_fingerprint("") == sha256(b"").hexdigest()


def test_evidence_is_deeply_immutable_and_copies_metadata():
    metadata = {"scope": {"roles": ["test-reader"]}}
    span = parse_text("测试段落", doc_id="doc", source="test://doc", metadata=metadata)[0]
    metadata["scope"]["roles"].append("other")
    assert span.metadata["scope"]["roles"] == ("test-reader",)
    with pytest.raises(FrozenInstanceError):
        span.content = "changed"
    with pytest.raises(TypeError):
        span.metadata["scope"]["roles"] = ()
    with pytest.raises(TypeError):
        parse_text("x", doc_id="doc", source="test://doc", metadata={"object": object()})


def test_stable_ids_include_document_version_source_and_position():
    kwargs = {"doc_id": "doc", "source": "test://a"}
    first = parse_text("相同\n\n相同", **kwargs)
    assert first == parse_text("相同\n\n相同", **kwargs)
    assert first[0].span_id != first[1].span_id
    assert first[0].span_id != parse_text("相同\n\n相同", doc_id="other", source="test://a")[0].span_id
    assert first[0].span_id != parse_text("相同\n\n相同", doc_id="doc", source="test://b")[0].span_id
    assert first[0].span_id != parse_text("相同\n\n相同\n", **kwargs)[0].span_id
    assert first[0].span_id == parse_text("相同\n\n相同", **kwargs, metadata={"tag": "new"})[0].span_id


def test_markdown_heading_hierarchy_resets_siblings_and_never_mixes_sections():
    spans = parse_markdown(
        "# 标题甲\n介绍甲\n## 子节甲\n内容甲\n### 深层\n深层内容\n"
        "## 子节乙\n内容乙\n# 标题乙\n结尾", doc_id="doc", source="test://headings",
    )
    assert [span.section_path for span in spans] == [
        ("标题甲",), ("标题甲", "子节甲"), ("标题甲", "子节甲", "深层"),
        ("标题甲", "子节乙"), ("标题乙",),
    ]
    assert spans[0].content == "章节：标题甲\n介绍甲"
    assert "内容甲" not in spans[3].content
    assert [(span.locator.start_line, span.locator.end_line) for span in spans] == [
        (2, 2), (4, 4), (6, 6), (8, 8), (10, 10),
    ]


def test_setext_headings_and_atx_closing_markers():
    spans = parse_markdown(
        "总标题\n===\n段落一\n\n子标题\n---\n段落二\n### 深节 ###\n段落三",
        doc_id="doc", source="test://setext",
    )
    assert [span.section_path for span in spans] == [
        ("总标题",), ("总标题", "子标题"), ("总标题", "子标题", "深节"),
    ]
    assert spans[2].locator.start_line == 9


def test_table_rows_are_self_contained_with_subject_headers_and_context():
    text = (
        "# 测试资料\n## 测试条件\n仅为解析测试的条件说明。\n\n"
        "| 样本 | 测量值 | 单位 |\n| --- | ---: | :--- |\n"
        "| SAMPLE-A | 17 | 测试单位 |\n| SAMPLE-B | 23 | 测试单位 |"
    )
    spans = parse_markdown(text, doc_id="test-table", source="test://table", metadata={"fixture": True})
    rows = [span for span in spans if span.locator.kind == "table_row"]
    assert len(rows) == 2
    row = rows[0]
    assert "样本：SAMPLE-A；测量值：17；单位：测试单位" in row.content
    assert "章节：测试资料 > 测试条件" in row.content
    assert "表格上下文：仅为解析测试的条件说明。" in row.content
    assert "SAMPLE-B" not in row.content
    assert row.locator == SourceLocator("test://table", 7, 7, "table_row", 5, 6, 3, 3)
    assert row.metadata["fixture"] is True
    assert row.doc_version == document_fingerprint(text)


def test_table_context_does_not_leak_across_heading_or_table():
    spans = parse_markdown(
        "# 节甲\n仅甲的条件\n# 节乙\n| 项 | 值 |\n| --- | --- |\n| B | 1 |\n\n"
        "| 项 | 值 |\n| --- | --- |\n| C | 2 |", doc_id="doc", source="test://no-leak",
    )
    rows = [span for span in spans if span.locator.kind == "table_row"]
    assert len(rows) == 2
    assert all("仅甲" not in span.content and "表格上下文" not in span.content for span in rows)
    assert all(span.section_path == ("节乙",) for span in rows)


def test_table_preserves_escaped_pipes_inline_code_and_missing_cells():
    spans = parse_markdown(
        "字段 | 内容 | 补充\n--- | --- | ---\na | x\\|y | `a|b`\nb | tail",
        doc_id="doc", source="test://escaped",
    )
    assert spans[0].content == "字段：a；内容：x|y；补充：`a|b`"
    assert spans[1].content == "字段：b；内容：tail；补充："
    with pytest.raises(ValueError, match="line 3"):
        parse_markdown("a | b\n--- | ---\nx | y | z", doc_id="doc", source="test://malformed")


def test_fenced_code_is_not_interpreted_as_heading_or_table():
    spans = parse_markdown(
        "# 外层\n```markdown\n# 非标题\n| a | b |\n| --- | --- |\n| 1 | 2 |\n```\n后续段落",
        doc_id="doc", source="test://code",
    )
    assert len(spans) == 2
    assert spans[0].locator.kind == "code"
    assert spans[0].section_path == spans[1].section_path == ("外层",)
    assert spans[0].locator.start_line == 2
    assert spans[0].locator.end_line == 7


def test_plain_text_paragraphs_keep_lines_and_literal_heading_text():
    spans = parse_text("\n# 普通文本\n第二行\n \t\n末段\n", doc_id="doc", source="test://text")
    assert len(spans) == 2
    assert spans[0].content == "# 普通文本\n第二行"
    assert spans[0].section_path == ()
    assert spans[0].locator == SourceLocator("test://text", 2, 3)
    assert spans[1].locator == SourceLocator("test://text", 5, 5)
    assert parse_text(" \n\t", doc_id="doc", source="test://text") == ()
    assert parse_markdown("# 标题\n\n", doc_id="doc", source="test://text") == ()


def test_tokenizer_preserves_ascii_models_and_overlapping_chinese_bigrams():
    tokenizer = ChineseTokenizer()
    assert tokenizer("配置测试型号 SAMPLE-X_2.0/A+1 与 SAMPLE-X_20") == (
        "配置", "置测", "测试", "试型", "型号", "sample-x_2.0/a+1", "与", "sample-x_20",
    )
    assert tokenizer("！ \n") == ()


def test_bm25_exact_model_does_not_match_model_prefix():
    exact = evidence("SAMPLE-X10 测试说明")
    prefix = evidence("SAMPLE-X100 测试说明")
    index = BM25Index([prefix, exact])
    assert [hit.evidence for hit in index.search("sample-x10")] == [exact]
    assert index.search("SAMPLE-X1") == ()


def test_aliases_apply_consistently_with_longest_match_and_ascii_boundaries():
    tokenizer = ChineseTokenizer({"测试别名": "SAMPLE-X10", "测试": "SAMPLE-OTHER", "sx": "SAMPLE-X10"})
    assert tokenizer("测试别名") == ("sample-x10",)
    assert tokenizer("SX") == ("sample-x10",)
    assert tokenizer("SXX SX-2") == ("sxx", "sx-2")
    canonical, alias = evidence("SAMPLE-X10"), evidence("测试别名")
    assert {hit.evidence.span_id for hit in BM25Index([canonical, alias], tokenizer=tokenizer).search("sx")} == {
        canonical.span_id, alias.span_id,
    }
    assert BM25Index([canonical]).search("测试别名") == ()
    with pytest.raises(ValueError):
        ChineseTokenizer({"": "SAMPLE-X10"})


def test_bm25_matches_independent_okapi_formula_with_length_normalization():
    short = evidence("needle needle other")
    long = evidence("needle other other other other")
    unrelated = evidence("other")
    index = BM25Index([short, long, unrelated], k1=1.2, b=0.75)
    results = index.search("needle needle")
    average_length = (3 + 5 + 1) / 3
    idf = math.log(1 + (3 - 2 + 0.5) / (2 + 0.5))
    expected_short = idf * 2 * 2.2 / (2 + 1.2 * (0.25 + 0.75 * 3 / average_length))
    expected_long = idf * 1 * 2.2 / (1 + 1.2 * (0.25 + 0.75 * 5 / average_length))
    assert [hit.evidence for hit in results] == [short, long]
    assert [hit.score for hit in results] == pytest.approx([expected_short, expected_long])
    assert index.search("needle") == results


def test_bm25_empty_unknown_and_scoped_corpus():
    permitted, excluded = evidence("needle", doc_id="allowed"), evidence("needle", doc_id="excluded")
    # This list represents the caller's pre-retrieval authorization decision.
    index = BM25Index([permitted])
    assert [hit.evidence for hit in index.search("needle")] == [permitted]
    assert excluded.span_id not in {hit.evidence.span_id for hit in index.search("needle")}
    assert index.search("") == index.search("unknown") == index.search("needle", top_k=0) == ()
    assert BM25Index([]).search("needle") == ()
    assert BM25Index([evidence("!!!")]).search("needle") == ()
    with pytest.raises(ValueError, match="duplicate"):
        BM25Index([permitted, permitted])
    with pytest.raises(ValueError):
        BM25Index([permitted], k1=0)
    with pytest.raises(ValueError):
        BM25Index([permitted], b=1.1)
    with pytest.raises(ValueError):
        index.search("needle", top_k=-1)


def test_bm25_ties_are_stable_independent_of_corpus_order():
    a, b = evidence("same", doc_id="a"), evidence("same", doc_id="b")
    assert BM25Index([a, b]).search("same") == BM25Index([b, a]).search("same")


def test_rrf_uses_stable_id_and_counts_once_per_route():
    a, b, c = evidence("a"), evidence("b"), evidence("c")
    a_copy = evidence("a")
    hits = reciprocal_rank_fusion([[a, a_copy, b], [ScoredEvidence(c, 999), ScoredEvidence(a_copy, -99)]], k=10)
    by_id = {hit.evidence.span_id: hit.score for hit in hits}
    assert len(hits) == 3
    assert hits[0].evidence == a
    assert by_id[a.span_id] == pytest.approx(1 / 11 + 1 / 12)
    assert by_id[b.span_id] == pytest.approx(1 / 12)
    assert by_id[c.span_id] == pytest.approx(1 / 11)
    assert reciprocal_rank_fusion([[a, a, b]], k=10) == reciprocal_rank_fusion([[a, b]], k=10)


def test_rrf_score_is_independent_of_route_iteration_order():
    target = evidence("target")
    fillers = [evidence(f"filler-{i}") for i in range(5)]
    routes = [fillers[:i] + [target] for i in range(6)]
    assert reciprocal_rank_fusion(routes) == reciprocal_rank_fusion(reversed(routes))


def test_rrf_ties_empty_rankings_and_limits():
    a, b = evidence("same", doc_id="a"), evidence("same", doc_id="b")
    first = reciprocal_rank_fusion([[a, b], [b, a]])
    assert first == reciprocal_rank_fusion([[b, a], [a, b]])
    assert [hit.evidence.span_id for hit in first] == sorted([a.span_id, b.span_id])
    assert reciprocal_rank_fusion([[], []]) == ()
    assert reciprocal_rank_fusion([]) == ()
    assert reciprocal_rank_fusion([[a]], top_k=0) == ()
    assert len(reciprocal_rank_fusion([[a, b]], top_k=1)) == 1
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[a]], k=-1)


@pytest.mark.parametrize(("left", "right", "expected"), [
    ([1, 0], [1, 0], 1), ([1, 0], [0, 1], 0), ([1, 0], [-1, 0], -1),
    ([0, 0], [1, 2], 0), ([], [], 0), ([1e300, 1e300], [1e300, 1e300], 1),
    ([1e-300, 0], [1e-300, 0], 1), ([1, 2], [2, 1], 0.8),
])
def test_cosine_similarity(left, right, expected):
    assert cosine_similarity(left, right) == pytest.approx(expected)


def test_cosine_dimension_and_finite_number_validation():
    for left, right in [([0, 0], [0]), ([], [0]), ([math.nan], [1]), ([1], [math.inf])]:
        with pytest.raises(ValueError):
            cosine_similarity(left, right)


def test_dense_search_scores_zero_vectors_and_validates_alignment():
    a, b, c = evidence("a"), evidence("b"), evidence("c")
    vectors = [[-1, 0], [1, 0], [0, 0]]
    hits = dense_search([1, 0], [a, b, c], vectors)
    assert [hit.evidence for hit in hits] == [b, c, a]
    assert [hit.score for hit in hits] == pytest.approx([1, 0, -1])
    assert vectors == [[-1, 0], [1, 0], [0, 0]]
    assert dense_search([0, 0], [a], [[1, 0]]) == ()
    assert dense_search([1, 0], [], []) == ()
    assert dense_search([1, 0], [a], [[1, 0]], top_k=0) == ()
    with pytest.raises(ValueError, match="one vector"):
        dense_search([1, 0], [a], [])
    with pytest.raises(ValueError, match="dimensions"):
        dense_search([0, 0], [a], [[0]])
    with pytest.raises(ValueError, match="duplicate"):
        dense_search([1, 0], [a, a], [[1, 0], [1, 0]])


@pytest.mark.parametrize(("start", "end"), [(0, 1), (3, 2), (-1, -1)])
def test_locator_rejects_invalid_line_ranges(start, end):
    with pytest.raises(ValueError):
        SourceLocator("test://doc", start, end)
