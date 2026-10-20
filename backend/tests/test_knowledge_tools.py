"""Offline regressions for constrained business tools; no LLM/database/network."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from app.services.knowledge.tools import (
    BusinessData,
    LoanInput,
    LoanEstimate,
    OfficialFactQuery,
    SourceReference,
    SourcedFact,
    SubjectQuery,
    ToolContext,
    ToolRegistry,
    ToolResult,
    calculate_loan,
)


def loan(**changes):
    return LoanInput.model_validate({
        "principal_yuan": "100000", "annual_rate_percent": "12", "term_months": 12,
        **changes,
    })


def context(**changes):
    return ToolContext(tenant_id="tenant-a", dealer_id="dealer-a", **changes)


def fact(**changes):
    now = datetime.now(timezone.utc)
    return SourcedFact.model_validate({
        "record_id": "test-record-1", "tenant_id": "tenant-a", "dealer_id": "dealer-a",
        "subject": "test-model", "fact_key": "list_price", "value": "123456.00",
        "unit": "CNY", "source": SourceReference(publisher="测试发布方", reference="test-document/page/2"),
        "valid_from": now - timedelta(days=1), "valid_until": now + timedelta(days=1),
        **changes,
    })


@pytest.mark.parametrize("principal,rate,months,payment,total,interest", [
    # Fixed independent amortization reference examples; do not recompute expected
    # values with the production formula in the test.
    ("100000", "12", 12, "8884.88", "106618.55", "6618.55"),
    ("1000000", "4.9", 360, "5307.27", "1910616.19", "910616.19"),
    # One period is independently P + P * annual_percent / 1200.
    ("1200", "12", 1, "1212.00", "1212.00", "12.00"),
])
def test_known_equal_payment_examples(principal, rate, months, payment, total, interest):
    result = calculate_loan(loan(principal_yuan=principal, annual_rate_percent=rate, term_months=months))
    assert result.monthly_payment_yuan == Decimal(payment)
    assert result.total_repayment_yuan == Decimal(total)
    assert result.total_interest_yuan == Decimal(interest)
    assert result.monthly_payment_yuan.as_tuple().exponent == -2
    assert isinstance(result.total_repayment_yuan, Decimal)


def test_zero_rate_and_half_up_rounding_without_interest_artifact():
    result = calculate_loan(loan(principal_yuan="1", annual_rate_percent="0", term_months=8))
    assert result.monthly_payment_yuan == Decimal("0.13")
    assert result.total_repayment_yuan == Decimal("1.00")
    assert result.total_interest_yuan == Decimal("0.00")
    thirds = calculate_loan(loan(principal_yuan="100", annual_rate_percent=0, term_months=3))
    assert thirds.monthly_payment_yuan == Decimal("33.33")
    assert thirds.total_repayment_yuan == Decimal("100.00")
    assert thirds.total_interest_yuan == Decimal("0.00")


def test_inputs_units_source_and_rounding_policy_are_explained():
    inputs = loan()
    result = calculate_loan(inputs)
    assert result.inputs == inputs
    assert result.source == "用户条件测算"
    assert result.currency == "CNY"
    assumptions = " ".join(result.assumptions)
    for term in ("元", "百分数", "月", "固定", "费用", "ROUND_HALF_UP", "未舍入", "分差", "不代表官方利率"):
        assert term in assumptions
    # Totals use the unrounded payment; they do not multiply rounded installments.
    assert result.monthly_payment_yuan * 12 != result.total_repayment_yuan
    dumped = result.model_dump(mode="json")
    assert dumped["monthly_payment_yuan"] == "8884.88"
    assert "official_rate" not in dumped


def test_decimal_context_is_local_and_small_valid_rate_is_stable():
    with localcontext() as external:
        external.prec = 6
        result = calculate_loan(loan(annual_rate_percent="0.00000001", term_months=600))
        assert result.monthly_payment_yuan == Decimal("166.67")
        assert external.prec == 6


@pytest.mark.parametrize("value", [True, False, "NaN", "sNaN", "Infinity", "-Infinity",
                                        float("nan"), float("inf"), float("-inf"),
                                        Decimal("NaN"), Decimal("Infinity"), None, [], {}, "x", ""])
@pytest.mark.parametrize("field", ["principal_yuan", "annual_rate_percent"])
def test_reject_non_finite_bool_and_non_numbers(field, value):
    with pytest.raises(ValidationError):
        loan(**{field: value})


@pytest.mark.parametrize("field,value", [
    ("principal_yuan", "0"), ("principal_yuan", "-1"),
    ("principal_yuan", "0.001"), ("principal_yuan", "1000000000.01"),
    ("principal_yuan", "1e1000000"), ("principal_yuan", "0e-1000000"),
    ("principal_yuan", "1" * 65), ("annual_rate_percent", "-0.01"),
    ("annual_rate_percent", "100.00000001"), ("annual_rate_percent", "0.000000001"),
    ("term_months", 0), ("term_months", -1), ("term_months", 601),
    ("term_months", True), ("term_months", False), ("term_months", "12"),
    ("term_months", 12.0), ("term_months", 12.5), ("term_months", float("nan")),
    ("term_months", float("inf")),
])
def test_reject_out_of_range_and_ambiguous_input(field, value):
    with pytest.raises(ValidationError):
        loan(**{field: value})


@pytest.mark.parametrize("principal,rate,months", [
    ("0.01", "0", 1), ("1000000000", "100", 600),
])
def test_documented_boundaries(principal, rate, months):
    result = calculate_loan(loan(principal_yuan=principal, annual_rate_percent=rate, term_months=months))
    assert result.total_repayment_yuan.is_finite()
    assert result.total_repayment_yuan >= result.inputs.principal_yuan


def test_normal_json_numbers_and_decimal_values_have_same_meaning():
    assert loan(principal_yuan=100000, annual_rate_percent=12.0) == loan()
    assert loan(annual_rate_percent=Decimal("12")) == loan()


def test_model_construct_cannot_bypass_validation_at_execution_boundary():
    unsafe = LoanInput.model_construct(principal_yuan=Decimal("NaN"), annual_rate_percent=Decimal("12"), term_months=12)
    with pytest.raises(ValidationError):
        calculate_loan(unsafe)


def test_every_model_and_exposed_schema_forbids_extra_fields():
    models = (LoanInput, LoanEstimate, SubjectQuery, OfficialFactQuery, SourceReference, SourcedFact, ToolContext, BusinessData, ToolResult)
    for model in models:
        assert model.model_json_schema()["additionalProperties"] is False
    registry = ToolRegistry()
    assert set(registry.tool_names) == {"calculate_loan", "get_official_fact", "quote", "inventory"}
    schemas = registry.input_schemas()
    for schema in schemas.values():
        assert schema["additionalProperties"] is False
        assert "context" not in schema["properties"]
        assert "tenant_id" not in schema["properties"]
    schemas.clear()
    assert len(registry.input_schemas()) == 4
    with pytest.raises(ValidationError):
        loan(official_rate=True)
    with pytest.raises(ValidationError):
        SourceReference(publisher="test", reference="test", url="https://example.invalid")


@pytest.mark.asyncio
async def test_registry_calculation():
    result = await ToolRegistry().execute("calculate_loan", loan().model_dump(), context=context())
    assert result.status == "ok"
    assert result.data.monthly_payment_yuan == Decimal("8884.88")


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["quote", "inventory"])
async def test_external_services_are_not_connected_by_default(tool):
    result = await ToolRegistry().execute(tool, {"subject": "test-model"}, context=context())
    assert result.status == "not_connected"
    assert result.data is None


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["execute_sql", "fetch_url", "__dict__", "delete", " quote", "quote ", "QUOTE"])
async def test_unknown_tools_cannot_dispatch(name):
    result = await ToolRegistry().execute(name, {"sql": "DROP TABLE customers", "url": "http://localhost"}, context=context())
    assert result.status == "unknown_tool"
    assert result.data is None


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,args", [
    ("calculate_loan", {"principal_yuan": "1", "annual_rate_percent": "0", "term_months": 1}),
    ("get_official_fact", {"subject": "test-model", "fact_key": "list_price"}),
    ("quote", {"subject": "test-model"}), ("inventory", {"subject": "test-model"}),
])
@pytest.mark.parametrize("override", ["tenant_id", "dealer_id", "context", "official_records", "url", "sql"])
async def test_user_cannot_override_trusted_context_or_supply_executors(tool, args, override):
    with pytest.raises(ValidationError):
        await ToolRegistry().execute(tool, {**args, override: "attacker-value"}, context=context())


@pytest.mark.asyncio
async def test_official_facts_require_caller_supplied_records():
    query = {"subject": "test-model", "fact_key": "list_price"}
    result = await ToolRegistry().execute("get_official_fact", query, context=context())
    assert result.status == "not_found"
    assert result.data is None
    supplied = fact()
    result = await ToolRegistry().execute("get_official_fact", query, context=context(official_records=(supplied,)))
    assert result.status == "ok"
    assert result.data.records == (supplied,)
    assert result.data.records[0].source.reference == "test-document/page/2"
    assert result.data.records[0].value == "123456.00"


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"tenant_id": "other-tenant"}, {"dealer_id": "other-dealer"},
    {"subject": "other-model"}, {"fact_key": "other-fact"},
    {"valid_from": datetime(2000, 1, 1, tzinfo=timezone.utc), "valid_until": datetime(2001, 1, 1, tzinfo=timezone.utc)},
    {"valid_from": datetime(2998, 1, 1, tzinfo=timezone.utc), "valid_until": datetime(2999, 1, 1, tzinfo=timezone.utc)},
])
async def test_official_fact_scope_and_validity_filter(changes):
    result = await ToolRegistry().execute(
        "get_official_fact", {"subject": "test-model", "fact_key": "list_price"},
        context=context(official_records=(fact(**changes),)),
    )
    assert result.status == "not_found"
    assert result.data is None


@pytest.mark.parametrize("changes", [
    {"source": None}, {"source": {"publisher": "", "reference": "x"}},
    {"source": {"publisher": "x", "reference": "   "}}, {"value": " "},
    {"valid_from": datetime(2000, 1, 1)}, {"valid_until": datetime(2000, 1, 1, tzinfo=timezone.utc)},
    {"official": True},
])
def test_malformed_or_unsourced_records_are_rejected(changes):
    with pytest.raises(ValidationError):
        fact(**changes)


class RecordingReadOnlyAPI:
    """Test-only adapter; production has no fallback business data."""

    def __init__(self, records):
        self.records = records
        self.calls = []

    async def quote(self, query, *, context):
        self.calls.append(("quote", query.subject, context.tenant_id, context.dealer_id))
        return BusinessData(records=self.records)

    async def inventory(self, query, *, context):
        self.calls.append(("inventory", query.subject, context.tenant_id, context.dealer_id))
        return BusinessData(records=self.records)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["quote", "inventory"])
async def test_real_adapter_contract_passes_trusted_scope_and_preserves_sources(tool):
    supplied = fact(fact_key=tool)
    api = RecordingReadOnlyAPI((supplied, fact(tenant_id="other")))
    result = await ToolRegistry(business_api=api).execute(tool, {"subject": "test-model"}, context=context())
    assert result.status == "ok"
    assert result.data.records == (supplied,)
    assert api.calls == [(tool, "test-model", "tenant-a", "dealer-a")]


@pytest.mark.asyncio
async def test_empty_adapter_response_is_unknown_not_zero_inventory():
    result = await ToolRegistry(business_api=RecordingReadOnlyAPI(())).execute(
        "inventory", {"subject": "test-model"}, context=context(),
    )
    assert result.status == "not_found"
    assert result.data is None


@pytest.mark.asyncio
async def test_invalid_or_unknown_calls_never_reach_adapter():
    api = RecordingReadOnlyAPI(())
    registry = ToolRegistry(business_api=api)
    with pytest.raises(ValidationError):
        await registry.execute("quote", {"subject": "test-model", "tenant_id": "other"}, context=context())
    assert (await registry.execute("execute_sql", {}, context=context())).status == "unknown_tool"
    assert api.calls == []


@pytest.mark.asyncio
async def test_unvalidated_nested_models_are_rejected_at_registry_boundary():
    invalid_record = fact().model_copy(update={"source": None})
    invalid_context = context().model_copy(update={"official_records": (invalid_record,)})
    with pytest.raises(ValidationError):
        await ToolRegistry().execute(
            "get_official_fact", {"subject": "test-model", "fact_key": "list_price"},
            context=invalid_context,
        )

    class InvalidAPI(RecordingReadOnlyAPI):
        async def quote(self, query, *, context):
            return BusinessData.model_construct(records=(invalid_record,))

    with pytest.raises(ValidationError):
        await ToolRegistry(business_api=InvalidAPI(())).execute("quote", {"subject": "test-model"}, context=context())


@pytest.mark.asyncio
async def test_adapter_failure_does_not_create_a_price_or_stock():
    class FailingAPI(RecordingReadOnlyAPI):
        async def quote(self, query, *, context):
            raise ConnectionError("offline test adapter")

    with pytest.raises(ConnectionError, match="offline test adapter"):
        await ToolRegistry(business_api=FailingAPI(())).execute("quote", {"subject": "test-model"}, context=context())
