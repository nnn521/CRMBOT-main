"""
报表 & 数据看板 API

提供销售数据驾驶舱所需的聚合数据，以及 LLM AI 解读功能。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func, distinct, case, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.conversation import Conversation
from app.models.chat_session_state import ChatSessionState
from app.models.db import get_db
from app.services.auth import get_current_user
from app.services.rate_limiter import enforce_rate_limit

logger = get_logger("api.reports")

router = APIRouter(prefix="/reports", tags=["reports"])


# ── 请求/响应模型 ──

class AnalyzeRequest(BaseModel):
    data: str  # dashboard JSON 字符串


class AnalyzeResponse(BaseModel):
    analysis: str


# ── GET /reports/dashboard ──

@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    返回报表看板所需的全部聚合数据。
    仅管理员可访问。
    """
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可访问")

    # ── 1. 状态分布 ──
    status_stmt = (
        select(ChatSessionState.status, func.count().label("cnt"))
        .group_by(ChatSessionState.status)
    )
    status_result = await db.execute(status_stmt)
    status_map: dict[str, int] = {}
    for row in status_result:
        status_map[row.status] = row.cnt

    total_sessions = sum(status_map.values())
    closed_count = status_map.get("closed", 0)
    active_count = status_map.get("active", 0)
    new_count = status_map.get("new", 0)
    # negotiating 可能不存在于当前 status 枚举，兼容处理
    negotiating_count = status_map.get("negotiating", 0)

    conversion_rate = round(closed_count / total_sessions * 100, 1) if total_sessions > 0 else 0
    active_customers = active_count + negotiating_count

    # ── 2. 本月新增线索 ──
    month_start_stmt = select(func.date_trunc("month", func.now()))
    month_start_result = await db.execute(month_start_stmt)
    month_start = month_start_result.scalar()

    new_leads_stmt = (
        select(func.count())
        .select_from(ChatSessionState)
        .where(ChatSessionState.updated_at >= month_start)
    )
    new_leads_result = await db.execute(new_leads_stmt)
    new_leads_this_month = new_leads_result.scalar() or 0

    # ── 3. 高意向客户数 ──
    high_intent_stmt = (
        select(func.count())
        .select_from(ChatSessionState)
        .where(ChatSessionState.high_intent_alerted == True)  # noqa: E712
    )
    high_intent_result = await db.execute(high_intent_stmt)
    high_intent_count = high_intent_result.scalar() or 0

    # ── 4. 月度趋势（按会话数） ──
    trend_stmt = (
        select(
            func.to_char(Conversation.created_at, "YYYY-MM").label("month"),
            func.count(distinct(Conversation.session_id)).label("count"),
        )
        .group_by(text("month"))
        .order_by(text("month"))
    )
    trend_result = await db.execute(trend_stmt)
    monthly_trend = [{"month": row.month, "count": row.count} for row in trend_result]

    # ── 5. 漏斗数据 ──
    funnel = {
        "total_leads": total_sessions,
        "contacted": active_count + negotiating_count,
        "interested": high_intent_count,
        "negotiating": negotiating_count,
        "closed": closed_count,
    }

    # ── 6. 状态分布 ──
    status_breakdown = {
        "new": new_count,
        "active": active_count,
        "negotiating": negotiating_count,
        "closed": closed_count,
        "lost": status_map.get("lost", 0),
    }

    return {
        "summary": {
            "total_sessions": total_sessions,
            "conversion_rate": conversion_rate,
            "active_customers": active_customers,
            "new_leads_this_month": new_leads_this_month,
        },
        "monthly_trend": monthly_trend,
        "funnel": funnel,
        "status_breakdown": status_breakdown,
    }


# ── GET /reports/deals ──

@router.get("/deals")
async def get_deals(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    limit: int = 10,
):
    """
    返回最近成交的会话列表。
    仅管理员可访问。
    """
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可访问")

    # 查询 closed 状态的会话
    stmt = (
        select(ChatSessionState)
        .where(ChatSessionState.status == "closed")
        .order_by(ChatSessionState.updated_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    closed_sessions = result.scalars().all()

    if not closed_sessions:
        return []

    # 获取每个 session 的 customer_name（从最新 user 消息的 metadata_json 中提取）
    session_ids = [s.session_id for s in closed_sessions]
    name_subq = (
        select(
            Conversation.session_id,
            Conversation.metadata_json,
            func.row_number()
            .over(
                partition_by=Conversation.session_id,
                order_by=Conversation.created_at.desc(),
            )
            .label("rn"),
        )
        .where(
            Conversation.session_id.in_(session_ids),
            Conversation.role == "user",
        )
        .subquery()
    )
    name_stmt = select(name_subq.c.session_id, name_subq.c.metadata_json).where(name_subq.c.rn == 1)
    name_result = await db.execute(name_stmt)

    name_map: dict[str, str] = {}
    for nr in name_result:
        meta = nr._mapping.get("metadata_json") or {}
        if isinstance(meta, dict):
            name = meta.get("customer_name")
            if name:
                name_map[nr.session_id] = name

    # 组装返回数据
    deals = []
    for s in closed_sessions:
        deals.append({
            "customer_name": name_map.get(s.session_id, "未知客户"),
            "title": f"会话 {s.session_id[:8]}...",
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "status": "已成交",
        })

    return deals


# ── POST /reports/analyze ──

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_report(
    req: AnalyzeRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    用 LLM 对报表数据生成 AI 解读和销售策略建议。
    仅管理员可访问。
    """
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可访问")
    await enforce_rate_limit(
        f"report:{current_user['user_id']}",
        limit=settings.report_rate_limit,
        window_seconds=settings.rate_limit_window_seconds,
    )

    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="未配置 LLM API Key")

    try:
        from langchain_openai import ChatOpenAI
        from langchain.schema import SystemMessage, HumanMessage

        llm = ChatOpenAI(
            model=settings.default_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.7,
        )

        system_prompt = """你是一位资深汽车销售数据分析师。
请根据以下销售看板数据，生成一段简洁的业务分析报告。

分析要点：
1. 整体转化率评估（好/中/差）
2. 漏斗各阶段转化情况，找出流失最大的环节
3. 月度趋势变化（增长/下降/平稳）
4. 给出2-3条具体可执行的销售策略建议

要求：
- 语言简洁专业，使用中文
- 控制在300字以内
- 不要重复原始数据，重点在于分析和建议"""

        user_prompt = f"以下是当前销售看板数据：\n\n{req.data}\n\n请生成分析报告："

        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        content = response.content if hasattr(response, "content") else str(response)

        return AnalyzeResponse(analysis=content)

    except Exception:
        logger.exception("AI 分析失败")
        raise HTTPException(status_code=502, detail="AI 分析服务暂不可用，请稍后重试")
