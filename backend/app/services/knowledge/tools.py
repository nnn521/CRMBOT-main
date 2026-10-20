"""Constrained, read-only business tools; no LLM, SQL, HTTP or default prices.

Only ``arguments`` is user-controlled. The authenticated server must construct
``ToolContext`` itself, including authorizing its tenant/dealer scope and verifying
any official records' provenance. Schema validation cannot authenticate a publisher.
Source references are opaque citation text: this module never opens them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from types import MappingProxyType
from typing import Annotated, Literal, Mapping, Protocol

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


class ToolSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, frozen=True, revalidate_instances="always",
        allow_inf_nan=False,
    )


def _decimal_input(value: object) -> Decimal:
    """Accept ordinary JSON numbers/decimal strings, never bool or non-finite data."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("expected a finite decimal number, not bool")
    text = str(value)
    if len(text) > 64:
        raise ValueError("decimal input is too long")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("expected a finite decimal number") from exc
    if not number.is_finite():
        raise ValueError("NaN and infinity are not permitted")
    # Bound exponent work before precision/range validation, even for zero.
    if abs(number.as_tuple().exponent) > 100:
        raise ValueError("decimal exponent is outside the supported range")
    return number


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
FactValue = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
PrincipalYuan = Annotated[
    Decimal, BeforeValidator(_decimal_input),
    Field(ge=Decimal("0.01"), le=Decimal("1000000000"), max_digits=12, decimal_places=2),
]
AnnualRatePercent = Annotated[
    Decimal, BeforeValidator(_decimal_input),
    Field(ge=Decimal("0"), le=Decimal("100"), max_digits=11, decimal_places=8),
]
Money = Annotated[Decimal, Field(ge=Decimal("0"), decimal_places=2)]


class LoanInput(ToolSchema):
    principal_yuan: PrincipalYuan = Field(description="贷款本金，人民币元；0.01 至 10 亿元，最多两位小数")
    annual_rate_percent: AnnualRatePercent = Field(
        description="用户给定的名义年利率百分数，如 4.8 表示 4.8%；0 至 100，最多八位小数"
    )
    term_months: Annotated[int, Field(ge=1, le=600)] = Field(description="还款期限，整数月，1 至 600")


class LoanEstimate(ToolSchema):
    inputs: LoanInput
    monthly_payment_yuan: Money
    total_repayment_yuan: Money
    total_interest_yuan: Money
    currency: Literal["CNY"] = "CNY"
    repayment_method: Literal["equal_payment"] = "equal_payment"
    source: Literal["用户条件测算"] = "用户条件测算"
    assumptions: tuple[str, ...]


def calculate_loan(inputs: LoanInput) -> LoanEstimate:
    """Equal principal-and-interest payment using Decimal throughout.

    Monthly rate = nominal annual percentage / 100 / 12. Totals use the
    unrounded theoretical payment, then each displayed amount rounds HALF_UP to
    cents. Monthly payment * months may therefore differ from the displayed total;
    this is an estimate, not a bank's cent-by-cent repayment schedule.
    """
    inputs = LoanInput.model_validate(inputs)
    with localcontext() as ctx:
        ctx.prec = 50
        ctx.rounding = ROUND_HALF_UP
        principal = inputs.principal_yuan
        months = inputs.term_months
        rate = inputs.annual_rate_percent / Decimal("1200")
        if rate == 0:
            payment = principal / months
            total = principal
        else:
            factor = (Decimal("1") + rate) ** months
            payment = principal * rate * factor / (factor - Decimal("1"))
            total = payment * months
        cent = Decimal("0.01")
        return LoanEstimate(
            inputs=inputs,
            monthly_payment_yuan=payment.quantize(cent),
            total_repayment_yuan=total.quantize(cent),
            total_interest_yuan=(total - principal).quantize(cent),
            assumptions=(
                "本金单位为人民币元；年利率为百分数；期限为月。",
                "名义年利率除以 100 再除以 12 得月利率，假设全期固定、每月期末等额还款。",
                "零利率时月供为本金除以期限，总利息为零。",
                "不含手续费、保险、税费、提前还款或其他银行费用。",
                "金额以 Decimal 计算，按 ROUND_HALF_UP 四舍五入至分；总额按未舍入月供计算后单独舍入，可能与展示月供乘期数有分差。",
                "仅按用户输入条件测算；不代表官方利率、银行报价或贷款承诺，实际以金融机构合同为准。",
            ),
        )


class SourceReference(ToolSchema):
    publisher: Text
    reference: Reference = Field(description="调用方已核验的文档编号、位置或 URL；仅作引用，不会访问")


class SourcedFact(ToolSchema):
    record_id: Text
    tenant_id: Text
    dealer_id: Text
    subject: Text
    fact_key: Text
    value: FactValue
    unit: Text | None = None
    source: SourceReference
    valid_from: AwareDatetime
    valid_until: AwareDatetime

    @model_validator(mode="after")
    def ordered_validity(self) -> SourcedFact:
        if self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be later than valid_from")
        return self


class ToolContext(ToolSchema):
    """Server-only scope and verified evidence; never deserialize from tool arguments.

    Official records must already be authenticated/authorized by the caller. Only
    matching tenant/dealer records in [valid_from, valid_until) can be returned.
    """

    tenant_id: Text
    dealer_id: Text
    official_records: Annotated[tuple[SourcedFact, ...], Field(max_length=1000)] = ()


class SubjectQuery(ToolSchema):
    subject: Text


class OfficialFactQuery(SubjectQuery):
    fact_key: Text


class BusinessData(ToolSchema):
    records: Annotated[tuple[SourcedFact, ...], Field(max_length=1000)]


class ReadOnlyBusinessAPI(Protocol):
    """Optional real adapter. Implement only read operations and preserve provenance.

    Adapter configuration/credentials/endpoints belong to the trusted server, not
    user arguments. Empty records mean unknown/unavailable data, never zero stock.
    """

    async def quote(self, query: SubjectQuery, *, context: ToolContext) -> BusinessData: ...

    async def inventory(self, query: SubjectQuery, *, context: ToolContext) -> BusinessData: ...


class ToolResult(ToolSchema):
    tool: Text
    status: Literal["ok", "unknown_tool", "not_connected", "not_found"]
    data: LoanEstimate | BusinessData | None = None
    message: Text | None = None


# No dynamic registration, arbitrary dispatch, eval, SQL or URL execution.
_INPUT_MODELS: Mapping[str, type[ToolSchema]] = MappingProxyType({
    "calculate_loan": LoanInput,
    "get_official_fact": OfficialFactQuery,
    "quote": SubjectQuery,
    "inventory": SubjectQuery,
})


class ToolRegistry:
    def __init__(self, *, business_api: ReadOnlyBusinessAPI | None = None) -> None:
        self._business_api = business_api

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(_INPUT_MODELS)

    def input_schemas(self) -> dict[str, dict[str, object]]:
        """Fresh JSON schemas describe user arguments only, excluding trusted context."""
        return {name: model.model_json_schema() for name, model in _INPUT_MODELS.items()}

    async def execute(
        self, tool_name: str, arguments: dict[str, object], *, context: ToolContext,
    ) -> ToolResult:
        """Validate before use; unknown tools cannot reach an adapter.

        Invalid parameters raise Pydantic ValidationError. Authentication and context
        construction belong to the server. All known tools require validated context.
        """
        # Validate tool names without coercion or allowing unbounded error echoes.
        SubjectQuery(subject=tool_name)
        tool = tool_name
        model = _INPUT_MODELS.get(tool)
        if model is None:
            return ToolResult(tool=tool, status="unknown_tool", message="工具不在只读白名单中")
        query = model.model_validate(arguments)
        context = ToolContext.model_validate(context)
        if tool == "calculate_loan":
            return ToolResult(tool=tool, status="ok", data=calculate_loan(query))
        if tool == "get_official_fact":
            records = context.official_records
        elif self._business_api is None:
            return ToolResult(tool=tool, status="not_connected", message="业务接口未接入，无法提供实时报价或库存")
        elif tool == "quote":
            response = BusinessData.model_validate(await self._business_api.quote(query, context=context))
            records = response.records
        else:  # The only remaining white-listed tool is inventory.
            response = BusinessData.model_validate(await self._business_api.inventory(query, context=context))
            records = response.records
        now = datetime.now(timezone.utc)
        matching = tuple(
            record for record in records
            if record.tenant_id == context.tenant_id
            and record.dealer_id == context.dealer_id
            and record.subject == query.subject
            and record.valid_from <= now < record.valid_until
            and (tool != "get_official_fact" or record.fact_key == query.fact_key)
        )
        if not matching:
            return ToolResult(tool=tool, status="not_found", message="没有匹配且在有效期内的有来源记录，不能推断官方事实或实时业务数据")
        return ToolResult(tool=tool, status="ok", data=BusinessData(records=matching))
