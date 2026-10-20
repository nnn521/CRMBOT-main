"""Offline synthesis contract tests; passing tests are not semantic evaluation."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import is_dataclass

import pytest

from app.services.knowledge.domain import Evidence, SourceLocator, document_fingerprint
from app.services.knowledge.evidence import GroundedAnswer
from app.services.knowledge.synthesis import (
    SynthesisAnswer,
    SynthesisAnswerService,
    SynthesisSelection,
)


def span(content: str, *, doc_id: str = "manual", line: int = 1) -> Evidence:
    return Evidence(doc_id, document_fingerprint(content), content, ("说明",),
                    SourceLocator(f"{doc_id}.md", line, line))


def claim(item: Evidence, text: str | None = None) -> dict:
    return {"text": item.content if text is None else text,
            "supports": [{"span_id": item.span_id, "quote": item.content}]}


def selection(*claims: dict) -> dict:
    return {"summary": "source_based_answer", "claims": list(claims)}


class FakeClient:
    def __init__(self, output=None, *, error: Exception | None = None, during=None):
        self.output = output
        self.error = error
        self.during = during
        self.calls: list[dict] = []

    async def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.during:
            self.during()
        if self.error:
            raise self.error
        return deepcopy(self.output)


def run(client: FakeClient, evidence, query="介绍一下这辆车", revalidate=lambda _: True):
    return asyncio.run(SynthesisAnswerService(client, revalidate=revalidate).answer(query, evidence))


def assert_unavailable(answer, reason):
    assert answer.status == "unavailable"
    assert answer.reason == reason
    assert answer.claims == answer.evidence_ids == answer.quotes == answer.dependencies == ()
    assert answer.claim_supports == ()
    assert answer.validation_scope == "structural_citations_only"


def test_success_natural_sentence_one_call_fixed_summary_and_full_citations():
    item = span("座舱配备全景天窗，后排座椅支持放倒。")
    natural = "这款车配有全景天窗，后排座椅也能放倒。"
    # This test demonstrates a paraphrase path, NOT that a paraphrase is entailed.
    client = FakeClient(selection(claim(item, natural)))
    checks = []

    async def revalidate(evidence):
        checks.append(evidence.span_id)
        return True

    answer = run(client, [item], revalidate=revalidate)
    assert answer.status == "ok"
    assert is_dataclass(answer) and isinstance(answer, SynthesisAnswer)
    assert not isinstance(answer, GroundedAnswer)
    assert answer.claims == (natural,)
    assert answer.summary == "以下回答依据所列来源整理。"
    assert answer.validation_scope == "structural_citations_only"
    assert answer.reason is None
    assert answer.evidence_ids == (item.span_id,)
    assert answer.claim_supports == ((item.span_id,),)
    assert answer.quotes[0].quote == item.content
    assert answer.quotes[0].locator == item.locator
    assert answer.dependencies == (answer.quotes[0].dependency,)
    assert checks == [item.span_id, item.span_id]
    assert len(client.calls) == 1
    call = client.calls[0]
    assert 0 < call["max_output_tokens"] <= 1600
    assert "输入安全规则" in call["system"]
    assert "不可信数据" in call["system"]
    assert call["data"]["query"].startswith("<user_message>")
    assert call["data"]["evidence"] == [{"span_id": item.span_id, "content": item.content}]
    assert call["data"]["output_schema"] == SynthesisSelection.model_json_schema()


def test_combines_two_sources_with_explicit_claim_mapping_and_deduplication():
    roof = span("座舱配备全景天窗。")
    seats = span("后排座椅支持放倒。", doc_id="seats")
    combined = {"text": "这辆车带全景天窗，后排座椅也能放倒。",
                "supports": [claim(roof)["supports"][0], claim(seats)["supports"][0]]}
    client = FakeClient(selection(combined, claim(seats, "后排座椅能放倒。")))
    answer = run(client, [roof, seats])
    assert answer.status == "ok"
    assert answer.evidence_ids == (roof.span_id, seats.span_id)
    assert len(answer.quotes) == 2
    assert answer.claim_supports == ((roof.span_id, seats.span_id), (seats.span_id,))
    assert len(client.calls) == 1


@pytest.mark.parametrize("tamper", ["unknown", "other_request", "partial", "changed_quote"])
def test_forged_or_non_full_citations_fail_closed(tamper):
    item = span("后排座椅支持放倒，但仅限停车时操作。")
    output = selection(claim(item))
    support = output["claims"][0]["supports"][0]
    if tamper == "unknown":
        support["span_id"] = "f" * 64
    elif tamper == "other_request":
        other = span("后排座椅支持放倒，但仅限停车时操作。", doc_id="not-retrieved")
        support["span_id"] = other.span_id
    elif tamper == "partial":
        support["quote"] = "后排座椅支持放倒"
    else:
        support["quote"] = "后排座椅不能放倒，但仅限停车时操作。"
    client = FakeClient(output)
    assert_unavailable(run(client, [item]), "invalid_output")
    assert len(client.calls) == 1


@pytest.mark.parametrize("source,text", [
    ("2025款 A7 的电池容量为80千瓦时。", "2025款 A7 的电池容量为90千瓦时。"),
    ("2025款 A7 的电池容量为80千瓦时。", "2026款 A7 的电池容量为80千瓦时。"),
    ("2025款 A7 配备全景天窗。", "2025款 A8 配备全景天窗。"),
    ("后排不支持加热。", "后排支持加热。"),
    ("后排支持加热。", "后排不支持加热。"),
    ("天窗仅限停车时操作。", "天窗可以随时操作。"),
])
def test_changed_number_year_model_or_negation_is_rejected_structurally(source, text):
    item = span(source)
    assert_unavailable(run(FakeClient(selection(claim(item, text))), [item]), "invalid_output")


@pytest.mark.parametrize("source,text", [
    ("2025款 A7 价格20万元，限本月到店客户。", "2025款 A7 价格20万元。"),
    ("2025款 A7 价格20万元，限本月到店客户。", "2025款 A7 价格25万元，限本月到店客户。"),
    # Both numbers occur: numeric matching cannot authorize reassigned roles.
    ("指导价25万元，优惠2万元，仅限本月。", "指导价2万元，优惠25万元，仅限本月。"),
    ("A7 暂无库存，A8 有现车。", "A7 有现车，A8 暂无库存。"),
    ("贷款年利率3%，需审批。", "审批无需通过，贷款年利率3%。"),
    ("整车质保3年，限非营运车辆。", "整车质保3年。"),
    ("仅限登记用户，承诺保留预约资格。", "承诺保留预约资格。"),
    ("Warranty lasts 3 years for private use only.", "Warranty lasts 3 years."),
])
def test_sensitive_claims_cannot_paraphrase_or_drop_conditions(source, text):
    item = span(source)
    assert_unavailable(run(FakeClient(selection(claim(item, text))), [item]), "invalid_output")


@pytest.mark.parametrize("source", [
    "售价20万元，限本月到店客户，不包含保险。",
    "当前暂无库存，到店后请重新确认。",
    "年利率3%，仅适用于审批通过的客户。",
    "质保3年，限非营运车辆。",
    "承诺保留预约资格，仅限已登记用户。",
    "|车型|价格|\n|A7|20万元|\n仅限本月到店客户。",
])
def test_sensitive_full_extract_preserves_all_original_conditions(source):
    item = span(source)
    answer = run(FakeClient(selection(claim(item))), [item])
    assert answer.status == "ok"
    assert answer.claims == (source,)
    assert answer.quotes[0].quote == source


def test_sensitive_question_cannot_make_ordinary_source_into_promise():
    item = span("后排座椅支持放倒。")
    answer = run(FakeClient(selection(claim(item, "后排座椅可以放倒。"))), [item], query="能承诺交车吗")
    assert_unavailable(answer, "invalid_output")


def test_fresh_revalidation_rejects_revoked_before_call():
    item = span("后排座椅支持放倒。")
    client = FakeClient(selection(claim(item)))
    assert_unavailable(run(client, [item], revalidate=lambda _: False), "evidence_unavailable")
    assert client.calls == []


def test_fresh_revalidation_rejects_revocation_during_generation():
    item = span("后排座椅支持放倒。")
    state = {"valid": True, "checks": 0}

    def check(_):
        state["checks"] += 1
        return state["valid"]

    client = FakeClient(selection(claim(item)), during=lambda: state.update(valid=False))
    assert_unavailable(run(client, [item], revalidate=check), "evidence_unavailable")
    assert len(client.calls) == 1 and state["checks"] == 2


@pytest.mark.parametrize("returned", [False, None, 1, "true"])
def test_only_literal_true_authorizes_generation(returned):
    item = span("后排座椅支持放倒。")
    client = FakeClient(selection(claim(item)))
    assert_unavailable(run(client, [item], revalidate=lambda _: returned), "evidence_unavailable")
    assert client.calls == []


@pytest.mark.parametrize("after_generation", [False, True])
def test_revalidation_exception_fails_closed(after_generation):
    item = span("后排座椅支持放倒。")
    checks = []

    async def check(_):
        checks.append(1)
        if not after_generation or len(checks) == 2:
            raise RuntimeError("storage unavailable")
        return True

    client = FakeClient(selection(claim(item)))
    assert_unavailable(run(client, [item], revalidate=check), "evidence_unavailable")
    assert len(client.calls) == int(after_generation)


def test_precheck_all_sources_postcheck_only_used_sources():
    used = span("后排座椅支持放倒。")
    other = span("座舱配备全景天窗。", doc_id="other")
    checked = []
    answer = run(FakeClient(selection(claim(used))), [used, other],
                 revalidate=lambda item: checked.append(item.span_id) or True)
    assert answer.status == "ok"
    assert set(checked[:2]) == {used.span_id, other.span_id}
    assert checked[2:] == [used.span_id]


@pytest.mark.parametrize("error", [TimeoutError("timeout"), RuntimeError("budget denied")])
def test_client_failure_or_budget_denial_has_no_retry(error):
    item = span("后排座椅支持放倒。")
    client = FakeClient(error=error)
    assert_unavailable(run(client, [item]), "model_failure")
    assert len(client.calls) == 1


@pytest.mark.parametrize("malformation", [
    "free_summary", "extra", "uncited", "unknown_support_field", "empty", "six_claims",
    "six_supports", "duplicate_support", "unavailable_with_claims", "string_claim", "list",
])
def test_strict_schema_rejects_invalid_output(malformation):
    item = span("后排座椅支持放倒。")
    output = selection(claim(item))
    if malformation == "free_summary":
        output["summary"] = "该车是最佳选择。"
    elif malformation == "extra":
        output["confidence"] = 1
    elif malformation == "uncited":
        output["claims"][0]["supports"] = []
    elif malformation == "unknown_support_field":
        output["claims"][0]["supports"][0]["verified"] = True
    elif malformation == "empty":
        output["claims"] = []
    elif malformation == "six_claims":
        output["claims"] = [claim(item, f"后排座椅可以放倒{'。' * i}") for i in range(1, 7)]
    elif malformation == "six_supports":
        output["claims"][0]["supports"] *= 6
    elif malformation == "duplicate_support":
        output["claims"][0]["supports"] *= 2
    elif malformation == "unavailable_with_claims":
        output["summary"] = "unavailable"
    elif malformation == "string_claim":
        output["claims"] = [item.content]
    else:
        output = []
    client = FakeClient(output)
    assert_unavailable(run(client, [item]), "invalid_output")
    assert len(client.calls) == 1


def test_total_citation_uses_bounded_across_claims():
    one = span("座舱配备全景天窗。")
    two = span("后排座椅支持放倒。", doc_id="two")
    supports = [claim(one)["supports"][0], claim(two)["supports"][0]]
    output = selection(*({"text": text, "supports": supports} for text in (
        "座舱有全景天窗，后排座椅能放倒。", "后排座椅能放倒，座舱带全景天窗。",
        "全景天窗与能放倒的后排座椅都有配备。",
    )))
    assert_unavailable(run(FakeClient(output), [one, two]), "invalid_output")


def test_no_selected_evidence_has_no_generated_prose():
    item = span("后排座椅支持放倒。")
    client = FakeClient({"summary": "unavailable", "claims": []})
    assert_unavailable(run(client, [item]), "no_selected_evidence")
    assert len(client.calls) == 1


def test_empty_and_over_budget_evidence_never_call_client_or_revalidator():
    client = FakeClient()

    def forbidden(_):
        pytest.fail("budget and empty checks must precede live access")

    assert_unavailable(run(client, [], revalidate=forbidden), "empty_evidence")
    assert_unavailable(run(client, [span("文" * 5400)], revalidate=forbidden), "evidence_budget_exceeded")
    # JSON keys/IDs/escaping count toward the 16KB inventory limit too.
    assert_unavailable(run(client, [span("a" * 15950)], revalidate=forbidden), "evidence_budget_exceeded")
    assert_unavailable(run(client, [span("x", doc_id=str(i)) for i in range(25)],
                           revalidate=forbidden), "evidence_budget_exceeded")
    assert client.calls == []


@pytest.mark.parametrize("query", ["", " ", "x" * 2001, None, 42])
def test_invalid_query_never_calls_client(query):
    client = FakeClient()
    with pytest.raises(ValueError):
        run(client, [], query=query)
    assert client.calls == []


def test_authoritative_revalidator_is_mandatory():
    with pytest.raises(TypeError):
        SynthesisAnswerService(FakeClient(), revalidate=None)


def test_schema_forbids_additional_fields_at_each_object_level():
    schema = SynthesisSelection.model_json_schema()
    assert schema["additionalProperties"] is False
    for name in ("SynthesisClaim", "QuoteSelection"):
        assert schema["$defs"][name]["additionalProperties"] is False
    assert schema["properties"]["claims"]["maxItems"] == 5
    assert schema["$defs"]["SynthesisClaim"]["properties"]["supports"]["minItems"] == 1
