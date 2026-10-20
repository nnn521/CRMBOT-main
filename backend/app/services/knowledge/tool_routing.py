"""Deterministic chat adapter for the read-only white-listed tools.

Call ``is_tool_query`` before an LLM intent classifier, then await
``tool_answer_bundle``. A None result means continue the ordinary RAG path,
including official list/MSRP prices. Returned bundles are complete replies, not
LLM prompts. Never build trusted_context from state.context, previous messages,
retrieved prices or model-extracted numbers. Only the current query supplies loan
conditions; all three must be explicit. No model/network/database calls are made
by this module (a deliberately injected real business adapter may perform reads).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import re

from pydantic import ValidationError

from app.services.knowledge.tools import (
    BusinessData,
    LoanEstimate,
    LoanInput,
    ToolContext,
    ToolRegistry,
)


_LOAN = re.compile(r"贷款|车贷|借款|本金|月供|等额本息|分期|还款|年利率|年化利率")
_INVENTORY = re.compile(r"库存|现车|现货|有货|有车吗|提车|交车时间")
_ACTUAL_PRICE = re.compile(r"门店价|到店价|成交价|落地价|裸车价|实际报价|实时报价|优惠|折扣|议价|最低价|底价|现金价|便宜")
_OFFICIAL_PRICE = re.compile(r"指导价|厂商建议(?:零售)?价|官方(?:价格|售价|报价|定价)|MSRP", re.I)
_GENERIC_PRICE = re.compile(r"报价|多少钱|价格|售价|卖多少")
_NUMBER = r"[+-]?[0-9]+(?:\.[0-9]+)?"
_PRINCIPAL_LABEL = re.compile(r"贷款(?:本金|金额)?|借款(?:本金|金额)?|本金")
_PRINCIPAL = re.compile(
    rf"(?:贷款(?:本金|金额)?|借款(?:本金|金额)?|本金)\s*(?:为|是|[:：=])?\s*"
    rf"(?P<number>{_NUMBER})\s*(?P<unit>万元|万|元)(?![A-Za-z0-9.元零〇一二两三四五六七八九十百千万亿])"
)
_RATE_LABEL = re.compile(r"年(?:化)?利率")
_RATE = re.compile(rf"年(?:化)?利率\s*(?:为|是|[:：=])?\s*(?P<number>{_NUMBER})\s*[%％](?![A-Za-z0-9.%％])")
_MONTHS = re.compile(
    r"(?<![A-Za-z0-9_.+\-零〇一二两三四五六七八九十百千万亿])(?:"
    r"(?:期限|期数|还款期|贷款期|分期)\s*(?:为|是|[:：=])?\s*(?P<labeled>[0-9]+)\s*(?:个)?月"
    r"|(?P<plain>[0-9]+)\s*个月)(?![供利息率份初末底])"
)
# Unparsed monetary/rate/duration alternatives must not silently disappear. This
# intentionally prefers a clarification over interpreting free-form finance text.
_OTHER_CONDITION = re.compile(r"[0-9一二三四五六七八九十百千万两零〇]+\s*(?:万元|万|元|[%％]|年|个月|期)")
_AMBIGUOUS = re.compile(r"或者|或|大约|大概|约为|大致|左右|上下|以上|以下|至少|至多|不超过|不少于|区间|介于|分别|不是|并非|不对|不要|别按|改为|改成|月利率|日利率|等额本金|先息后本|递增|递减|浮动|LPR|[<>≤≥]", re.I)
_LOAN_REASON_TEXT = {
    "missing_explicit_conditions": "缺少当前消息中明确且带单位的贷款条件，未进行测算。",
    "multiple_or_conflicting_conditions": "存在多组或冲突的贷款条件，未选择其中一组测算。",
    "ambiguous_or_unsupported_conditions": "贷款条件含区间、近似值或暂不支持的还款方式，未进行测算。",
    "invalid_conditions": "贷款条件超出支持范围或数值无效，未进行测算。",
}
_LOAN_HELP = (
    "请在当前消息中明确提供唯一的一组条件：贷款本金（元或万元）、年利率（百分数，如4.8%）、"
    "期限（整数月，如36个月）。请用阿拉伯数字并注明单位；零利率请明确写年利率0%。"
    "不会从车型价格、首付、历史消息或上下文猜测本金、利率和期限。"
)


@dataclass(frozen=True, slots=True)
class LoanConditions:
    inputs: LoanInput | None
    missing: tuple[str, ...] = ()
    reason: str | None = None


def _query(query: str) -> str:
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise ValueError("query must contain 1–2000 characters")
    return query.strip()


def _requests(query: str) -> tuple[bool, bool, bool]:
    loan = bool(_LOAN.search(query))
    inventory = bool(_INVENTORY.search(query))
    quote = bool(_ACTUAL_PRICE.search(query) or (
        _GENERIC_PRICE.search(query) and not _OFFICIAL_PRICE.search(query)
    ))
    return loan, inventory, quote


def is_tool_query(query: str) -> bool:
    """Pure recognition, suitable before any paid intent call. MSRP stays in RAG."""
    return any(_requests(_query(query)))


def parse_loan_conditions(query: str) -> LoanConditions:
    """Only explicit principal+annual percentage+integer months; no context input.

    Supports e.g. 本金100000元，年利率4.8%，36个月 or 贷款10万元，年利率0%，12个月.
    Chinese digits, annual terms, monthly rates, implicit units, multiple scenarios
    and qualified/range values require clarification instead of best-effort math.
    """
    query = _query(query)
    principal = list(_PRINCIPAL.finditer(query))
    rates = list(_RATE.finditer(query))
    months = list(_MONTHS.finditer(query))
    missing = tuple(label for label, matches in (
        ("贷款本金（元）", principal), ("年利率（百分数）", rates), ("期限（整数月）", months),
    ) if not matches)
    if missing:
        return LoanConditions(None, missing, "missing_explicit_conditions")
    if any(len(matches) != 1 for matches in (principal, rates, months)):
        return LoanConditions(None, reason="multiple_or_conflicting_conditions")
    if len(_PRINCIPAL_LABEL.findall(query)) != 1 or len(_RATE_LABEL.findall(query)) != 1:
        return LoanConditions(None, reason="multiple_or_conflicting_conditions")
    remainder = query
    for match in sorted(principal + rates + months, key=lambda item: item.start(), reverse=True):
        remainder = remainder[:match.start()] + " " + remainder[match.end():]
    if (_AMBIGUOUS.search(query) or _OTHER_CONDITION.search(remainder)
            or re.search(r"[0-9]\s*(?:至|到|[-~～—–/])\s*[0-9]", query)):
        return LoanConditions(None, reason="ambiguous_or_unsupported_conditions")
    # Prevent parsing a lower bound as the whole condition (e.g. 本金10万至20万)
    # and prevent surrounding approximation/negation from becoming an assertion.
    if (re.search(r"(?:约|近|超|低于|高于|不到|超过|至少|至多)\s*(?:贷款|本金|年利率|[0-9])", query)
            or any(re.search(r"(?:大约|约|近|不|非|负|小于|大于|超过|不到)\s*$", query[:m.start()])
                   for m in principal + rates + months)):
        return LoanConditions(None, reason="ambiguous_or_unsupported_conditions")
    try:
        term_text = months[0].group("labeled") or months[0].group("plain")
        if any(len(text) > 64 for text in (
            principal[0].group("number"), rates[0].group("number"), term_text,
        )):
            return LoanConditions(None, reason="invalid_conditions")
        with localcontext() as ctx:
            ctx.prec = 80
            amount = Decimal(principal[0].group("number"))
            if principal[0].group("unit") in ("万", "万元"):
                amount *= 10000
        inputs = LoanInput(
            principal_yuan=amount,
            annual_rate_percent=rates[0].group("number"),
            term_months=int(term_text),
        )
    except (ValidationError, ValueError, ArithmeticError):
        return LoanConditions(None, reason="invalid_conditions")
    return LoanConditions(inputs)


def _bundle() -> dict:
    # Computation is not a RAG source. Never fabricate span IDs, release IDs or
    # citation URLs to satisfy the frontend's source-document citation contract.
    return {
        "reply": "", "citations": [], "knowledge_results": [],
        "knowledge_release_id": None, "answer_status": "unavailable",
        "data_as_of": datetime.now(timezone.utc).isoformat(),
        "assumptions": [], "limitations": ["本回复仅包含确定性业务工具结果；测算和业务引用不属于知识库来源引文。"],
        "tool_status": "not_connected", "tools": [],
    }


def _loan_reply(estimate: LoanEstimate) -> str:
    inputs = estimate.inputs
    return (
        f"按你明确提供的条件估算：贷款本金{inputs.principal_yuan:,.2f}元，"
        f"年利率{inputs.annual_rate_percent:f}%，期限{inputs.term_months}个月，采用等额本息。\n"
        f"月供约{estimate.monthly_payment_yuan:,.2f}元，"
        f"还款总额约{estimate.total_repayment_yuan:,.2f}元，"
        f"利息总额约{estimate.total_interest_yuan:,.2f}元。\n"
        "来源：用户条件测算。仅为估算，假设全期固定利率，不含手续费、保险、税费等其他费用。"
        "金额四舍五入到分，总额按未舍入月供计算后单独舍入，展示月供乘期数可能有分差。"
        "不代表官方利率、银行报价或贷款承诺，实际以金融机构合同为准。"
    )


async def tool_answer_bundle(
    query: str, *, trusted_context: ToolContext | None = None,
    registry: ToolRegistry | None = None,
) -> dict | None:
    """Return a final bundle for tools, or None to continue RAG.

    The server may inject a real registry ONLY with separately authenticated
    trusted_context. State/context business numbers are never accepted/used here.
    Without injection the registry has no external adapter. Its local context is
    only a namespace for local arithmetic/unconnected checks, never authorization.
    Business records retain their real source references as text, not fake RAG
    citations; callers must not feed these replies into another LLM to regenerate.
    """
    query = _query(query)
    wants_loan, wants_inventory, wants_quote = _requests(query)
    if not any((wants_loan, wants_inventory, wants_quote)):
        return None
    bundle = _bundle()
    replies: list[str] = []
    statuses: list[str] = []
    # Use a separate server parameter only; no context/history/business mapping
    # appears in this signature, so callers cannot accidentally merge those values.
    context = (ToolContext.model_validate(trusted_context) if trusted_context is not None
               else ToolContext(tenant_id="local-estimate", dealer_id="not-connected"))
    active_registry = registry if registry is not None else ToolRegistry()
    if wants_loan:
        parsed = parse_loan_conditions(query)
        if parsed.inputs is None:
            replies.append("当前贷款条件缺失、存在歧义或超出支持范围，暂不能计算。" + _LOAN_HELP)
            bundle["limitations"].append(_LOAN_REASON_TEXT[parsed.reason])
            bundle["tools"].append({"tool": "calculate_loan", "status": "clarification", "missing": list(parsed.missing)})
            statuses.append("clarification")
        else:
            result = await active_registry.execute("calculate_loan", parsed.inputs.model_dump(), context=context)
            bundle["tools"].append(result.model_dump(mode="json"))
            if result.status == "ok" and isinstance(result.data, LoanEstimate):
                replies.append(_loan_reply(result.data))
                bundle["assumptions"].extend(result.data.assumptions)
                statuses.append("ok")
            else:
                replies.append("贷款测算暂时不可用，无法给出可靠结果。")
                statuses.append("unavailable")
    for tool, wanted, label in (("inventory", wants_inventory, "实时库存"), ("quote", wants_quote, "门店优惠及实际报价")):
        if not wanted:
            continue
        if registry is not None and trusted_context is None:
            replies.append(f"{label}查询缺少服务端已认证的门店上下文，当前无法查询。")
            bundle["limitations"].append(f"{label}缺少服务端已认证的业务上下文，本次未查询。")
            bundle["tools"].append({"tool": tool, "status": "not_connected"})
            statuses.append("not_connected")
            continue
        # The raw current question is an opaque subject, never an endpoint or SQL.
        # Long free-form subjects are not sent to real adapters as guessed models.
        subject = query if len(query) <= 200 else "未明确的车型或业务条件"
        result = await active_registry.execute(tool, {"subject": subject}, context=context)
        bundle["tools"].append(result.model_dump(mode="json"))
        statuses.append(result.status)
        if result.status == "ok" and isinstance(result.data, BusinessData):
            replies.append(f"{label}接口返回以下当前有效记录：\n" + "\n".join(
                f"{record.subject}：{record.fact_key}={record.value}"
                f"{(' ' + record.unit) if record.unit else ''}；来源：{record.source.publisher}，{record.source.reference}"
                for record in result.data.records
            ))
            bundle["limitations"].append("业务记录附其发布方和来源编号；这些来源文本不是知识库原文引用链接。")
        elif result.status == "not_connected":
            replies.append(f"{label}接口尚未接入，无法确认实时库存、可用优惠或实际成交金额。"
                           "官方指导价与实际门店成交价不同，不能用指导价或旧资料替代实时业务数据。")
            bundle["limitations"].append(f"{label}接口尚未接入，本次未获取实时业务数据。")
        else:
            replies.append(f"目前没有可用于确认{label}的有效有来源记录，不能推断库存或成交金额。")
            bundle["limitations"].append(f"{label}没有匹配且有效的有来源记录，本次未能确认。")
    if _OFFICIAL_PRICE.search(query):
        bundle["limitations"].append("官方指导价需通过有来源的知识检索另行确认，本次工具回复未提供指导价。")
        replies.append("官方指导价需另行通过有来源的知识检索确认，本次工具回复未提供指导价。")
    bundle["reply"] = "\n\n".join(replies)
    if "clarification" in statuses:
        bundle.update(answer_status="clarification", tool_status="clarification")
    elif all(status == "ok" for status in statuses) and not _OFFICIAL_PRICE.search(query):
        bundle.update(answer_status="answered", tool_status="ok")
    elif "ok" in statuses:
        bundle.update(answer_status="partial", tool_status="partial")
    elif "not_connected" in statuses:
        bundle["tool_status"] = "not_connected"
    else:
        bundle["tool_status"] = "unavailable"
    return bundle
