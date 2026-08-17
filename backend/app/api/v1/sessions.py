"""
聚合聊天会话 API - CRUD 接口

端点：
- GET    /api/v1/sessions           → 列出所有会话
- POST   /api/v1/sessions           → 创建新会话
- GET    /api/v1/sessions/{id}      → 获取会话详情
- PATCH  /api/v1/sessions/{id}      → 更新会话
- DELETE /api/v1/sessions/{id}      → 删除会话
- GET    /api/v1/sessions/{id}/messages → 获取会话消息
- POST   /api/v1/sessions/{id}/handover → 切换 AI/人工 模式
- POST   /api/v1/sessions/{id}/handover/suggest → AI 生成建议回复
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logging import get_logger
from app.models.db import get_db
from app.models.session import Session
from app.models.conversation import Conversation
from app.services.auth import get_current_user
from app.services.ws_manager import manager

logger = get_logger("api.sessions")

router = APIRouter()


# ═════════════════════════════════════════════════════════════════
# Pydantic Schemas
# ═════════════════════════════════════════════════════════════════

class SessionCreate(BaseModel):
    """创建会话请求体"""
    title: str = Field(..., min_length=1, max_length=255, description="会话标题")
    customer_name: Optional[str] = Field(None, max_length=128, description="客户名称")


class SessionUpdate(BaseModel):
    """更新会话请求体（所有字段可选）"""
    title: Optional[str] = Field(None, min_length=1, max_length=255, description="会话标题")
    status: Optional[str] = Field(
        None,
        pattern="^(new|active|negotiating|closed|lost)$",
        description="状态: new / active / negotiating / closed / lost"
    )
    customer_name: Optional[str] = Field(None, max_length=128, description="客户名称")
    handover_mode: Optional[str] = Field(
        None,
        pattern="^(ai|human)$",
        description="接管模式: ai / human",
    )


class SessionOut(BaseModel):
    """会话响应体"""
    id: str
    title: str
    status: str
    customer_name: Optional[str] = None
    handover_mode: str = "ai"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    """消息响应体"""
    id: int
    role: str
    content: str
    intent: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ═════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════

def _session_to_out(s: Session) -> SessionOut:
    """将 ORM 模型转换为 Pydantic 输出模型"""
    return SessionOut(
        id=str(s.id),
        title=s.title,
        status=s.status,
        customer_name=s.customer_name,
        handover_mode=getattr(s, "handover_mode", "ai"),
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


# ═════════════════════════════════════════════════════════════════
# Endpoints
# ═════════════════════════════════════════════════════════════════

@router.get(
    "/sessions",
    response_model=dict,
    summary="列出所有聚合聊天会话（B端管理员）",
)
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = Query(None, alias="status", description="按状态筛选"),
    limit: int = Query(50, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="分页偏移"),
    current_user: dict = Depends(get_current_user),
):
    """列出所有聚合聊天会话，支持状态筛选与分页（仅管理员）"""
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")
    
    stmt = select(Session).order_by(Session.updated_at.desc())

    if status_filter:
        stmt = stmt.where(Session.status == status_filter)

    stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    sessions = result.scalars().all()

    return {
        "sessions": [_session_to_out(s) for s in sessions],
        "total": len(sessions),
    }


@router.post(
    "/sessions",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="创建聚合聊天会话",
)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建新的聚合聊天会话（仅管理员）"""
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")
    session = Session(
        id=uuid.uuid4(),
        title=body.title,
        customer_name=body.customer_name,
        status="new",
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    logger.info(f"会话已创建: {session.id} - {session.title}")

    return {"session": _session_to_out(session)}


@router.get(
    "/sessions/{session_id}",
    response_model=dict,
    summary="获取会话详情",
)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取单个聚合聊天会话的详情（仅管理员）"""
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话 {session_id} 不存在"
        )

    return {"session": _session_to_out(session)}


@router.patch(
    "/sessions/{session_id}",
    response_model=dict,
    summary="更新会话",
)
async def update_session(
    session_id: uuid.UUID,
    body: SessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新聚合聊天会话（标题 / 状态 / 客户名称）（仅管理员）"""
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话 {session_id} 不存在"
        )

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未提供任何更新字段"
        )

    for field, value in update_data.items():
        setattr(session, field, value)

    session.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(session)

    logger.info(f"会话已更新: {session.id} → {update_data}")

    return {"session": _session_to_out(session)}


@router.delete(
    "/sessions/{session_id}",
    response_model=dict,
    summary="删除会话",
)
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除聚合聊天会话（关联的 conversations 的 agg_session_id 会被置为 NULL）（仅管理员）"""
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话 {session_id} 不存在"
        )

    await db.delete(session)
    await db.flush()

    logger.info(f"会话已删除: {session_id}")

    return {"status": "deleted", "session_id": str(session_id)}


@router.get(
    "/sessions/{session_id}/messages",
    response_model=dict,
    summary="获取会话关联的消息",
)
async def get_session_messages(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="分页偏移"),
    current_user: dict = Depends(get_current_user),
):
    """Deprecated legacy endpoint retained only to return an explicit migration error."""
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")
    # 先确认会话存在
    session_result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    if not session_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"会话 {session_id} 不存在"
        )

    # Conversation no longer has an agg_session_id relationship. Returning a
    # clear 410 avoids the former AttributeError and directs clients to the
    # canonical string-based chat-session API.
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="此旧聚合会话接口已废弃，请使用 /api/v1/chat/sessions/{session_id}/messages",
    )


# ═════════════════════════════════════════════════════════════════
# Handover 端点已迁移到 chat.py (Issue #11 修复)
# /chat/sessions/{id}/handover — 统一的 chat session handover
# 旧端点 /sessions/{id}/handover 已移除（UUID vs 字符串体系不兼容）
# ═══════════════════════════════════════════════════════════════==
