"""Deterministic routing tests; entirely offline and no LLM invocation."""

from decimal import Decimal

import pytest

from app.services.knowledge.tool_routing import (
    is_tool_query,
    parse_loan_conditions,
    tool_answer_bundle,
)
from app.services.knowledge.tools import ToolContext, ToolRegistry


@pytest.mark.parametrize("query", [
    "凯美瑞的官方指导价是多少？", "厂商建议零售价是多少", "汉兰达MSRP", "官方报价和配置",
    "介绍一下安全配置", "保修多长时间", "2025款油耗多少",
])
@pytest.mark.asyncio
async def test_official_prices_and_general_facts_continue_rag(query):
    assert not is_tool_query(query)
    assert await tool_answer_bundle(query) is None


@pytest.mark.parametrize("query", [
    "凯美瑞今天有现车吗", "库存还有多少", "何时提车", "门店优惠多少", "实际报价多少钱",
    "官方指导价与成交价分别多少", "凯美瑞多少钱", "月供多少", "贷款方案", "车贷年利率是多少",
])
def test_tool_recognition(query):
    assert is_tool_query(query)


@pytest.mark.parametrize("query,principal,rate,months", [
    ("贷款本金100000元，年利率12%，期限12个月，算月供", "100000", "12", 12),
    ("贷款10万元，年利率4.8%，36个月", "100000", "4.8", 36),
    ("本金：10万；年化利率：0％；期限：12月", "100000", "0", 12),
    ("计算等额本息，本金1200元，年利率12%，1个月", "1200", "12", 1),
])
def test_only_explicit_user_conditions_are_parsed(query, principal, rate, months):
    parsed = parse_loan_conditions(query)
    assert parsed.inputs is not None
    assert parsed.inputs.principal_yuan == Decimal(principal)
    assert parsed.inputs.annual_rate_percent == Decimal(rate)
    assert parsed.inputs.term_months == months
    assert parsed.missing == ()


@pytest.mark.parametrize("query", [
    "凯美瑞月供多少", "首付3万，分期36个月，算月供", "贷款10万，36个月", "本金10万，利率4.8，36个月",
    "本金100000，年利率4.8%，36个月", "贷款十万元，年利率百分之四点八，三十六个月",
    "本金十万元，年利率4.8%，36个月", "本金10万，年利率4.8%，三十六个月",
    "本金10万，年利率4.8%，3年", "本金10万，年利率4.8%，36期",
    "本金10万，月利率0.4%，36个月", "本金10万，年利率4.8%，期限3.5个月",
    "本金10万，年利率4.8%，-36个月", "本金10万，年利率4.8%，期限+36个月",
    "本金10万，年利率4.8%，11月份提车", "本金10万，年利率4.8%，36月底",
    "本金10万，年利率4.8%，3.6e1个月", "本金10万，年利率NaN%，36个月",
    "本金Inf元，年利率4.8%，36个月", "本金10万，年利率Infinity%，36个月",
    "本金10万，年利率true%，36个月", "本金0元，年利率4.8%，36个月",
    "本金-10万，年利率4.8%，36个月", "本金10万，年利率-4.8%，36个月",
    "本金10万，年利率101%，36个月", "本金10万，年利率4.8%，601个月",
    "本金10万元，年利率4.8%，0个月", "本金10万元亿元，年利率4.8%，36个月",
    "本金10万五，年利率4.8%，36个月", "本金10万，年利率4.8%，三6个月",
])
def test_missing_chinese_or_invalid_conditions_never_compute(query):
    assert parse_loan_conditions(query).inputs is None


@pytest.mark.parametrize("query", [
    "本金10万或20万，年利率4.8%，36个月", "本金10万至20万，年利率4.8%，36个月",
    "本金10-20万元，年利率4.8%，36个月", "本金约10万，年利率4.8%，36个月",
    "本金10万左右，年利率4.8%，36个月", "本金10万以上，年利率4.8%，36个月",
    "本金10万，年利率4.8%以上，36个月", "本金10万，年利率4.8%-5%，36个月",
    "本金10万，年利率4.8%，36个月或48个月", "本金10万，年利率4.8%，期限36至48个月",
    "本金10万，年利率4.8%，36个月；本金20万，年利率5%，48个月",
    "本金10万，年利率4.8%，36个月，等额本金", "本金10万，年利率4.8%，36个月，浮动利率",
    "本金10万不对，年利率4.8%，36个月", "不要计算本金10万，年利率4.8%，36个月",
    "本金10万，年利率4.8%，36个月，另外首付3万元",
])
def test_ambiguous_or_multiple_scenarios_require_clarification(query):
    assert parse_loan_conditions(query).inputs is None


@pytest.mark.asyncio
async def test_calculation_bundle_has_conditions_and_no_fake_citations():
    result = await tool_answer_bundle("贷款本金100000元，年利率12%，期限12个月，算月供")
    assert result["answer_status"] == "answered"
    assert result["tool_status"] == "ok"
    assert result["citations"] == []
    assert result["knowledge_results"] == []
    assert result["knowledge_release_id"] is None
    assert result["data_as_of"]
    for text in ("100,000.00元", "12%", "12个月", "8,884.88元", "用户条件测算", "不代表官方利率", "仅为估算", "等额本息"):
        assert text in result["reply"]
    assert result["assumptions"]
    assert result["tools"][0]["tool"] == "calculate_loan"
    assert result["tools"][0]["data"]["inputs"]["principal_yuan"] == "100000"


@pytest.mark.asyncio
async def test_zero_rate_route():
    result = await tool_answer_bundle("贷款本金1元，年利率0%，8个月")
    assert result["answer_status"] == "answered"
    assert "0.13元" in result["reply"]
    assert result["tools"][0]["data"]["total_interest_yuan"] == "0.00"


class RecordingRegistry(ToolRegistry):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def execute(self, name, arguments, *, context):
        self.calls.append((name, arguments, context))
        return await super().execute(name, arguments, context=context)


@pytest.mark.asyncio
async def test_missing_conditions_never_call_registry_or_use_context_values():
    registry = RecordingRegistry()
    result = await tool_answer_bundle("凯美瑞月供多少", registry=registry)
    assert result["answer_status"] == "clarification"
    assert result["tool_status"] == "clarification"
    assert "阿拉伯数字" in result["reply"]
    assert "年利率0%" in result["reply"]
    assert registry.calls == []
    assert result["citations"] == []
    # The function intentionally has no state.context/history/business-value input.
    with pytest.raises(TypeError):
        await tool_answer_bundle("贷款月供多少", context={"principal_yuan": 100000, "annual_rate_percent": 4.8, "term_months": 36})


@pytest.mark.asyncio
@pytest.mark.parametrize("query,tool", [
    ("凯美瑞库存多少", "inventory"), ("凯美瑞门店优惠多少", "quote"), ("凯美瑞实际报价多少", "quote"),
])
async def test_business_unconnected_default_is_explicit(query, tool):
    result = await tool_answer_bundle(query)
    assert result["answer_status"] == "unavailable"
    assert result["tool_status"] == "not_connected"
    assert result["tools"][0]["tool"] == tool
    assert result["tools"][0]["status"] == "not_connected"
    assert "接口尚未接入" in result["reply"]
    assert "官方指导价与实际门店成交价不同" in result["reply"]
    assert result["citations"] == []
    assert result["knowledge_results"] == []


@pytest.mark.asyncio
async def test_all_execution_uses_white_registry_and_separate_server_context():
    registry = RecordingRegistry()
    trusted = ToolContext(tenant_id="server-tenant", dealer_id="server-dealer")
    result = await tool_answer_bundle("贷款本金100000元，年利率12%，12个月", registry=registry, trusted_context=trusted)
    assert result["answer_status"] == "answered"
    assert len(registry.calls) == 1
    assert registry.calls[0][0] == "calculate_loan"
    assert registry.calls[0][2] == trusted
    # No loan amount is inferred from trusted or untrusted business data.
    result = await tool_answer_bundle("贷款月供多少", registry=registry, trusted_context=trusted)
    assert result["answer_status"] == "clarification"
    assert len(registry.calls) == 1


@pytest.mark.asyncio
async def test_injected_business_registry_requires_explicit_server_context():
    registry = RecordingRegistry()
    result = await tool_answer_bundle("库存多少", registry=registry)
    assert result["tool_status"] == "not_connected"
    assert any("缺少服务端已认证的业务上下文" in item for item in result["limitations"])
    assert registry.calls == []


@pytest.mark.asyncio
async def test_mixed_loan_and_business_request_does_not_hide_limitations():
    result = await tool_answer_bundle("本金100000元，年利率12%，12个月，算月供，门店优惠多少")
    assert result["answer_status"] == "partial"
    assert result["tool_status"] == "partial"
    assert "8,884.88元" in result["reply"]
    assert "接口尚未接入" in result["reply"]
    assert result["citations"] == []


@pytest.mark.asyncio
async def test_mixed_official_and_dealer_price_never_relabels_list_price():
    result = await tool_answer_bundle("官方指导价和实际门店优惠分别是多少")
    assert result["tool_status"] == "not_connected"
    assert any("本次工具回复未提供指导价" in item for item in result["limitations"])
    assert "本次工具回复未提供指导价" in result["reply"]


@pytest.mark.asyncio
async def test_all_visible_limitations_are_chinese_and_mixed_requests_are_partial():
    result = await tool_answer_bundle("本金100000元，年利率12%，12个月，官方指导价是多少，还有库存和门店优惠")
    assert result["answer_status"] == "partial"
    assert "实时库存接口尚未接入" in result["reply"]
    assert "门店优惠及实际报价接口尚未接入" in result["reply"]
    assert "本次工具回复未提供指导价" in result["reply"]
    assert all(any("一" <= char <= "鿿" for char in item) for item in result["limitations"])
    assert "official_list_price_requires_rag" not in result["limitations"]
    only_official_mixed = await tool_answer_bundle("本金100000元，年利率12%，12个月，官方指导价是多少")
    assert only_official_mixed["answer_status"] == "partial"


@pytest.mark.parametrize("query", [None, True, "", "  ", "a" * 2001])
def test_invalid_query_is_not_coerced(query):
    with pytest.raises(ValueError):
        is_tool_query(query)
    with pytest.raises(ValueError):
        parse_loan_conditions(query)
