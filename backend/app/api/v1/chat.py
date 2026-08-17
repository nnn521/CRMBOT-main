"""
聊天 API 模块 - 核心接口 POST /api/v1/chat

这是前端（微信小程序）与后端交互的主要接口。
"""

import time
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.agents.graphs import run_sales_agent
from app.api.deps import get_current_session, verify_wechat_token
from app.core.config import settings
from app.services.auth import get_current_user
from app.core.logging import get_logger
from app.services.ws_manager import manager
from app.services.image_service import find_car_images
from app.services.rate_limiter import enforce_rate_limit
from app.models.chat import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    DocumentInfo,
    DocumentType,
    MessageRole,
    UserIntent,
)
from app.models.conversation import Conversation
from app.models.chat_session_state import ChatSessionState
from app.models.db import get_db, get_db_optional

logger = get_logger("api.chat")

router = APIRouter()

async def _get_or_create_session_state(db: AsyncSession, session_id: str):
    """获取或创建会话运行时状态（替代内存 dict/set）"""
    result = await db.execute(
        select(ChatSessionState).where(ChatSessionState.session_id == session_id)
    )
    state = result.scalar_one_or_none()
    if not state:
        state = ChatSessionState(
            session_id=session_id,
            handover_mode="ai",
            high_intent_alerted=False,
            status="active",
        )
        db.add(state)
        await db.flush()
    return state


async def _assert_session_owner(
    db: Optional[AsyncSession], session_id: str, current_user: dict
) -> None:
    """Prevent a customer from sending messages into another customer's session."""
    if current_user.get("role") == "admin":
        return
    username = current_user.get("username", "")
    if session_id == f"session_{username}":
        return
    if db is None:
        # Chat authentication already requires PostgreSQL; fail closed if the
        # ownership source is unexpectedly unavailable.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="会话服务不可用")
    owner = await db.execute(
        select(Conversation.id).where(
            Conversation.session_id == session_id,
            Conversation.user_open_id == str(current_user["user_id"]),
            Conversation.role == "user",
        ).limit(1)
    )
    if owner.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该会话")


def _find_car_images(user_message: str, context: dict, intent) -> list[str]:
    """Compatibility wrapper around the shared multi-model image matcher."""
    image_intents = {"product_inquiry", "general_chat"}
    intent_val = getattr(intent, "value", str(intent)) if intent else ""
    if intent_val not in image_intents:
        return []
    wants_gallery = any(word in user_message for word in ("图片", "照片", "实拍", "十款", "多款"))
    return find_car_images(
        user_message,
        context,
        fallback_to_popular=wants_gallery,
    )


def _ws_message_payload(
    *,
    message_id: str,
    session_id: str,
    role: str,
    content: str,
    timestamp: Optional[datetime] = None,
    documents: Optional[list] = None,
    images: Optional[list[str]] = None,
    intent: Optional[str] = None,
) -> dict:
    """Build the canonical message shape shared by REST history and WebSocket."""
    return {
        "id": str(message_id),
        "session_id": session_id,
        "role": role,
        "content": content,
        "timestamp": (timestamp or datetime.now()).isoformat(),
        "documents": documents or [],
        "images": images or [],
        "intent": intent,
    }


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="智能销售助手对话接口",
    description="""
    智能销售 AI Agent 的核心对话接口。
    
    支持的场景：
    - 💬 普通对话（问候、闲聊）
    - 📦 产品咨询（基于知识库 RAG）
    - 💰 价格谈判（销售话术支持）
    - 📄 生成报价单（Excel）
    - 📋 创建提案书（Word）
    - 📝 起草合同（Word）
    - 📊 数据分析报表（Excel）
    - 📽️ 生成演示文稿（PPT大纲）
    
    示例请求：
    ```json
    {
        "session_id": "wx_user_openid_123",
        "message": "帮我生成一份报价单，客户是张三科技",
        "history": [],
        "context": {
            "sales_rep_name": "李明",
            "department": "企业销售部"
        }
    }
    ```
    """
)
async def chat(
    request: ChatRequest,
    session_id: str = Depends(get_current_session),
    authorization: Optional[str] = Header(None),
    current_user: Optional[dict] = Depends(get_current_user),
    db = Depends(get_db_optional),
) -> ChatResponse:
    """
    处理用户消息，调用 LangGraph Agent 生成回复
    
    Args:
        request: 聊天请求数据
        session_id: 会话ID（从 Header 或请求体获取）
        authorization: 微信登录凭证
    
    Returns:
        包含 AI 回复、意图识别、建议操作等的响应
    """
    # Require authentication — C端 must be logged in
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录"
        )
    await enforce_rate_limit(
        f"chat:{current_user['user_id']}",
        limit=settings.chat_rate_limit,
        window_seconds=settings.rate_limit_window_seconds,
    )
    
    start_time = time.time()
    
    # Use request session_id, tie it to the authenticated user
    actual_session_id = request.session_id or session_id
    await _assert_session_owner(db, actual_session_id, current_user)
    
    logger.info(
        f"[Session: {actual_session_id}] 用户 {current_user['username']}"
        f"(id={current_user['user_id']}) 发送消息，长度={len(request.message)}"
    )
    
    try:
        # 转换历史消息格式
        history = []
        for msg in request.history:
            history.append({
                "role": msg.role.value,
                "content": msg.content,
            })
        
        # ═══ Issue #1 修复：检查接管模式（DB持久化） ═══
        handover_mode = "ai"
        if db is not None:
            state = await _get_or_create_session_state(db, actual_session_id)
            handover_mode = state.handover_mode
            requests_human = any(
                keyword in request.message
                for keyword in ("转人工", "人工客服", "人工服务", "真人客服")
            )
            if requests_human and handover_mode != "human":
                state.handover_mode = "human"
                state.updated_at = datetime.now()
                handover_mode = "human"
                logger.info("[Session: %s] 客户主动请求转人工", actual_session_id)
                handover_event = {
                    "type": "handover_update",
                    "session_id": actual_session_id,
                    "mode": "human",
                }
                await manager.broadcast_to_session(actual_session_id, handover_event)
                await manager.broadcast_to_session("admin", handover_event)
        logger.info("[Session: %s] 当前接管模式: %s", actual_session_id, handover_mode)
        if handover_mode == "human":
            # 人工模式：只保存消息，不调用 AI
            message_id = f"human-user-{uuid4()}"
            message_time = datetime.now()
            if db is not None:
                try:
                    user_msg = Conversation(
                        session_id=actual_session_id,
                        user_open_id=str(current_user["user_id"]),
                        role="user",
                        content=request.message,
                        intent="human_mode",
                        metadata_json={"customer_name": current_user["username"]},
                    )
                    db.add(user_msg)
                    await db.flush()
                    message_id = str(user_msg.id)
                    message_time = user_msg.created_at or message_time
                except Exception as e:
                    logger.warning(f"Failed to persist human-mode message: {e}")

            # Broadcast user message to admin (without AI reply)
            await manager.broadcast_to_session(
                "admin",
                {
                    "type": "new_message",
                    "session_id": actual_session_id,
                    "message": _ws_message_payload(
                        message_id=message_id,
                        session_id=actual_session_id,
                        role="user",
                        content=request.message,
                        timestamp=message_time,
                        intent="human_mode",
                    ),
                }
            )
            await manager.broadcast_to_session(
                "admin",
                {
                    "type": "session_update",
                    "session_id": actual_session_id,
                    "customer_name": current_user["username"],
                    "last_message": request.message[:50],
                    "timestamp": datetime.now().isoformat(),
                }
            )

            return ChatResponse(
                session_id=actual_session_id,
                user_message_id=message_id,
                status="waiting_human",
                reply="",
                intent=UserIntent.UNKNOWN,
                documents=[],
                images=[],
                suggested_actions=[],
                metadata={"handover_mode": "human", "status": "等待人工回复"},
                response_time_ms=int((time.time() - start_time) * 1000),
            )

        # 运行 Agent 工作流
        final_state = await run_sales_agent(
            session_id=actual_session_id,
            message=request.message,
            context=request.context,
            history=history,
        )
        
        # 计算响应时间
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # 构建响应
        intent = final_state.get("intent_analysis")
        intent_value = intent.intent if intent else UserIntent.UNKNOWN
        
        # 确保文档列表格式正确（LangGraph流式处理后可能是dict）
        raw_docs = final_state.get("generated_documents", [])
        docs = []
        for d in raw_docs if isinstance(raw_docs, list) else []:
            if isinstance(d, dict):
                fn = d.get("file_name", d.get("filename", "文档.xlsx"))
                docs.append(DocumentInfo(
                    doc_type=DocumentType(d.get("doc_type", d.get("type", "xlsx"))),
                    file_name=fn,
                    file_path=f"/api/v1/documents/{fn}",
                ))
            elif hasattr(d, 'file_name'):
                # 强制替换路径为API端点
                d = DocumentInfo(
                    doc_type=getattr(d, 'doc_type', DocumentType.XLSX),
                    file_name=d.file_name,
                    file_path=f"/api/v1/documents/{d.file_name}",
                )
                docs.append(d)
        
        logger.info(f"[Session: {actual_session_id}] 文档数: {len(docs)}")

        # 匹配车型图片
        images = final_state.get("images") or _find_car_images(
            user_message=request.message,
            context=final_state.get("context", {}),
            intent=intent_value,
        )

        response = ChatResponse(
            session_id=actual_session_id,
            reply=final_state.get("sales_response", "抱歉，我没有理解您的问题。"),
            intent=intent_value,
            documents=docs,
            images=images,
            suggested_actions=final_state.get("suggested_actions", []),
            metadata={
                "knowledge_results_count": len(final_state.get("knowledge_results", [])),
                "document_params": final_state.get("document_params"),
                "error": final_state.get("error"),
            },
            response_time_ms=response_time_ms,
        )
        
        # Persist messages to Conversation table for session list queries
        user_message_id = f"user-{uuid4()}"
        assistant_message_id = f"assistant-{uuid4()}"
        user_message_time = datetime.now()
        assistant_message_time = datetime.now()
        intent_str = intent_value.value if hasattr(intent_value, 'value') else str(intent_value)
        if db is not None:
            try:
                user_msg = Conversation(
                    session_id=actual_session_id,
                    user_open_id=str(current_user["user_id"]),
                    role="user",
                    content=request.message,
                    intent=intent_str,
                    metadata_json={"customer_name": current_user["username"]},
                )
                assistant_msg = Conversation(
                    session_id=actual_session_id,
                    user_open_id=str(current_user["user_id"]),
                    role="assistant",
                    content=response.reply,
                    intent=intent_str,
                    metadata_json={
                        "documents": [
                            {"file_name": document.file_name, "doc_type": document.doc_type.value}
                            for document in docs
                        ]
                    },
                )
                db.add(user_msg)
                db.add(assistant_msg)
                await db.flush()
                user_message_id = str(user_msg.id)
                assistant_message_id = str(assistant_msg.id)
                user_message_time = user_msg.created_at or user_message_time
                assistant_message_time = assistant_msg.created_at or assistant_message_time
            except Exception as e:
                logger.warning(f"Failed to persist messages: {e}")

        response.user_message_id = user_message_id
        response.message_id = assistant_message_id

        user_event = {
            "type": "new_message",
            "session_id": actual_session_id,
            "message": _ws_message_payload(
                message_id=user_message_id,
                session_id=actual_session_id,
                role="user",
                content=request.message,
                timestamp=user_message_time,
                intent=intent_str,
            ),
        }
        assistant_event = {
            "type": "new_message",
            "session_id": actual_session_id,
            "message": _ws_message_payload(
                message_id=assistant_message_id,
                session_id=actual_session_id,
                role="assistant",
                content=response.reply,
                timestamp=assistant_message_time,
                documents=[doc.model_dump(by_alias=True) for doc in docs],
                images=images,
                intent=intent_str,
            ),
        }
        
        # Broadcast to WebSocket clients watching this session (C端)
        await manager.broadcast_to_session(
            actual_session_id,
            assistant_event,
        )
        # Notify admin dashboard about session update (B端实时刷新)
        await manager.broadcast_to_session(
            "admin",
            {
                "type": "session_update",
                "session_id": actual_session_id,
                "customer_name": current_user["username"],
                "last_message": request.message[:50],
                "timestamp": datetime.now().isoformat(),
            }
        )
        # B端 receives each persisted message as an independent event.
        await manager.broadcast_to_session("admin", user_event)
        await manager.broadcast_to_session("admin", assistant_event)
        # ═══ Issue #3/#4 修复：高意向提醒去重（DB持久化） ═══
        is_high_intent = getattr(intent, "high_intent", False) if intent else False
        if is_high_intent and db is not None:
            state = await _get_or_create_session_state(db, actual_session_id)
            if not state.high_intent_alerted:
                state.high_intent_alerted = True
                await db.flush()
                await manager.broadcast_to_session(
                    "admin",
                    {
                        "type": "high_intent_alert",
                        "session_id": actual_session_id,
                        "customer_name": current_user["username"],
                        "trigger_message": request.message[:200],
                        "intent": intent_value.value if hasattr(intent_value, "value") else str(intent_value),
                        "timestamp": datetime.now().isoformat(),
                    },
                )
                logger.info(f"[Session: {actual_session_id}] 高意向提醒已广播")

        logger.info(
            f"[Session: {actual_session_id}] 响应完成，"
            f"意图: {intent_value.value}, 耗时: {response_time_ms}ms"
        )
        
        return response
        
    except Exception as e:
        logger.exception("[Session: %s] 处理失败", actual_session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="消息处理失败，请稍后重试",
        )


# ── Chat sessions (for admin session list) ──

class ChatSessionOut(BaseModel):
    """聊天会话摘要 — 给B端管理员展示"""
    session_id: str = Field(..., description="C端客户会话ID")
    last_message_preview: str = Field(..., description="最后一条消息预览")
    last_updated: Optional[str] = Field(None, description="最后更新时间")
    message_count: int = Field(0, description="消息总数")
    customer_name: Optional[str] = Field(None, description="客户用户名")
    status: str = Field("active", description="会话状态: new/active/negotiating/closed/lost")
    handover_mode: str = Field("ai", description="接管模式: ai / human")


@router.get(
    "/chat/sessions",
    summary="获取聊天会话列表（B端管理员）",
    description="查询 conversations 表中所有唯一 session_id，附带最后一条消息预览，按最近更新排序"
)
async def list_chat_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    limit: int = 50,
):
    """
    返回所有活跃聊天会话的摘要信息。
    仅管理员可访问。
    """
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")

    # 获取每个 session_id 的最新一条消息（用窗口函数避免重复）
    subq = (
        select(
            Conversation.session_id,
            Conversation.content,
            Conversation.created_at,
            func.row_number()
            .over(
                partition_by=Conversation.session_id,
                order_by=Conversation.created_at.desc(),
            )
            .label("rn"),
            func.count(Conversation.id)
            .over(partition_by=Conversation.session_id)
            .label("msg_count"),
        )
        .subquery()
    )

    stmt = (
        select(subq.c.session_id, subq.c.content, subq.c.created_at, subq.c.msg_count)
        .where(subq.c.rn == 1)
        .order_by(subq.c.created_at.desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    # ── 获取每个 session 的 customer_name ──
    # 从最新一条 user 角色的 metadata_json 中提取
    name_map: dict[str, str] = {}
    if rows:
        session_ids = [row.session_id for row in rows]
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
        for nr in name_result:
            meta = nr._mapping.get("metadata_json") or {}
            if isinstance(meta, dict):
                name = meta.get("customer_name")
                if name:
                    name_map[nr.session_id] = name

    # Batch-load session state from DB
    session_ids = [row.session_id for row in rows]
    state_map: dict[str, ChatSessionState] = {}
    if session_ids:
        state_result = await db.execute(
            select(ChatSessionState).where(ChatSessionState.session_id.in_(session_ids))
        )
        for s in state_result.scalars().all():
            state_map[s.session_id] = s

    items = [
        ChatSessionOut(
            session_id=row.session_id,
            last_message_preview=row.content[:80] if row.content else "",
            last_updated=row.created_at.isoformat() if row.created_at else None,
            message_count=row.msg_count,
            customer_name=name_map.get(row.session_id),
            status=state_map[row.session_id].status if row.session_id in state_map else "active",
            handover_mode=state_map[row.session_id].handover_mode if row.session_id in state_map else "ai",
        )
        for row in rows
    ]
    return {"sessions": items, "total": len(items)}


@router.get(
    "/chat/sessions/{session_id}/messages",
    summary="获取指定会话的消息记录（B端）",
    description="查询 conversations 表中指定 session_id 的所有消息，按时间升序"
)
async def get_chat_session_messages(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    limit: int = 100,
):
    """管理员可读取任意会话；客户只能读取自己的会话。"""
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    if current_user.get("role") != "admin":
        expected_session = f"session_{current_user.get('username')}"
        owner_check = await db.execute(
            select(Conversation.id).where(
                Conversation.session_id == session_id,
                Conversation.user_open_id == str(current_user["user_id"]),
                Conversation.role == "user",
            ).limit(1)
        )
        if session_id != expected_session and owner_check.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该会话")

    stmt = (
        select(Conversation)
        .where(Conversation.session_id == session_id)
        .order_by(Conversation.created_at.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()

    return {
        "session_id": session_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
        "total": len(messages),
    }


@router.post(
    "/chat/stream",
    summary="流式对话接口（预留）",
    description="WebSocket 或 SSE 流式响应接口，用于实时显示思考过程"
)
async def chat_stream(
    request: ChatRequest,
    session_id: str = Depends(get_current_session),
):
    """
    流式对话接口（开发中）
    
    用于实现打字机效果，实时显示 Agent 的思考过程。
    """
    # TODO: 实现 WebSocket 或 SSE 流式响应
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="流式接口开发中"
    )


@router.get("/chat/history", summary="获取当前客户的会话历史")
async def list_customer_history(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    session_result = await db.execute(
        select(distinct(Conversation.session_id)).where(
            Conversation.user_open_id == str(current_user["user_id"]),
            Conversation.role == "user",
        )
    )
    items = []
    for session_id in session_result.scalars().all():
        latest_result = await db.execute(
            select(Conversation)
            .where(Conversation.session_id == session_id)
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        latest = latest_result.scalar_one_or_none()
        count_result = await db.execute(
            select(func.count(Conversation.id)).where(Conversation.session_id == session_id)
        )
        if latest:
            items.append({
                "session_id": session_id,
                "preview": latest.content[:50],
                "updated_at": latest.created_at.isoformat() if latest.created_at else None,
                "message_count": count_result.scalar_one(),
            })
    items.sort(key=lambda item: item["updated_at"] or "", reverse=True)
    return {"sessions": items, "total": len(items)}


@router.get(
    "/chat/history/{session_id}",
    summary="获取对话历史",
    description="获取指定会话的历史消息记录"
)
async def get_chat_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    owner = await db.execute(
        select(Conversation.id).where(
            Conversation.session_id == session_id,
            Conversation.user_open_id == str(current_user["user_id"]),
            Conversation.role == "user",
        ).limit(1)
    )
    if owner.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    result = await db.execute(
        select(Conversation)
        .where(Conversation.session_id == session_id)
        .order_by(Conversation.created_at.asc())
    )
    messages = result.scalars().all()
    return {
        "session_id": session_id,
        "messages": [
            {"id": str(m.id), "role": m.role, "content": m.content, "created_at": m.created_at}
            for m in messages
        ],
        "total": len(messages),
    }


@router.delete(
    "/chat/history/{session_id}",
    summary="清除对话历史",
    description="清除指定会话的所有历史记录"
)
async def clear_chat_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    清除对话历史
    """
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    owner = await db.execute(
        select(Conversation.id).where(
            Conversation.session_id == session_id,
            Conversation.user_open_id == str(current_user["user_id"]),
            Conversation.role == "user",
        ).limit(1)
    )
    if owner.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    await db.execute(delete(Conversation).where(Conversation.session_id == session_id))
    await db.execute(delete(ChatSessionState).where(ChatSessionState.session_id == session_id))
    logger.info(f"[Session: {session_id}] 对话历史已清除")
    return {
        "session_id": session_id,
        "status": "cleared",
    }


# ═════════════════════════════════════════════════════════════════
# 销售接管 (Handover) — Chat Session 运行时状态
# 状态持久化到 chat_session_state 表，不再使用内存 dict/set
# ═════════════════════════════════════════════════════════════════


@router.post(
    "/chat/high-intent/{session_id}/dismiss",
    summary="管理员处理高意向提醒后，允许该会话再次触发提醒（DB持久化）",
)
async def dismiss_high_intent_alert(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")
    state = await _get_or_create_session_state(db, session_id)
    state.high_intent_alerted = False
    await db.flush()
    return {"session_id": session_id, "status": "dismissed"}


class HandoverRequest(BaseModel):
    """切换接管模式请求体"""
    mode: str = Field(..., pattern="^(ai|human)$", description="接管模式: ai / human")


class HumanMessageRequest(BaseModel):
    """人工客服发送消息请求体"""
    message: str


@router.post(
    "/chat/sessions/{session_id}/handover",
    summary="切换 AI/人工 接管模式 (Chat Session)",
)
async def handover_chat_session(
    session_id: str,
    body: HandoverRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """切换聊天会话的接管模式（AI ↔ 人工），通过 WebSocket 广播状态变更"""
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")

    # Get customer name (if session has conversations)
    cust_result = await db.execute(
        select(Conversation.metadata_json)
        .where(Conversation.session_id == session_id, Conversation.role == "user")
        .order_by(Conversation.created_at.asc())
        .limit(1)
    )
    cust_row = cust_result.scalar_one_or_none()
    customer_name = "客户"
    if cust_row and isinstance(cust_row, dict):
        customer_name = cust_row.get("customer_name", "客户")

    state = await _get_or_create_session_state(db, session_id)
    old_mode = state.handover_mode
    state.handover_mode = body.mode
    state.updated_at = datetime.now()
    await db.flush()

    logger.info(f"聊天会话 {session_id} 接管模式切换: {old_mode} → {body.mode}")

    # WebSocket broadcast
    event = {
        "type": "handover_update",
        "session_id": session_id,
        "mode": body.mode,
        "customer_name": customer_name,
        "timestamp": datetime.now().isoformat(),
    }
    await manager.broadcast_to_session(session_id, event)
    await manager.broadcast_to_session("admin", event)

    return {"session_id": session_id, "handover_mode": body.mode}


@router.post(
    "/chat/sessions/{session_id}/human-message",
    summary="人工客服发送消息，推送到 C端",
)
async def human_message(
    session_id: str,
    body: HumanMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """人工客服在接管模式下发送消息，直接推送给 C端客户，不调 AI"""
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")

    # 保存消息为 assistant 角色（代表人工客服回复）
    agent_msg = Conversation(
        session_id=session_id,
        user_open_id=str(current_user["user_id"]),
        role="assistant",
        content=body.message,
        intent="human_mode",
        metadata_json={"sender": "agent", "agent_name": current_user.get("username", "客服")},
    )
    db.add(agent_msg)
    await db.flush()

    message_payload = _ws_message_payload(
        message_id=str(agent_msg.id),
        session_id=session_id,
        role="assistant",
        content=body.message,
        timestamp=agent_msg.created_at,
        intent="human_mode",
    )

    # 广播到 C端 session 频道（让客户收到）
    logger.info("[HUMAN-MSG] session=%s message_id=%s", session_id, agent_msg.id)
    await manager.broadcast_to_session(
        session_id,
        {
            "type": "new_message",
            "session_id": session_id,
            "message": message_payload,
        },
    )

    # 广播到 admin 频道（让 B端同步显示，只发 assistant 副本，不发 user_message）
    await manager.broadcast_to_session(
        "admin",
        {
            "type": "new_message",
            "session_id": session_id,
            "message": message_payload,
        },
    )

    # 触发 B端更新会话列表预览
    await manager.broadcast_to_session(
        "admin",
        {
            "type": "session_update",
            "session_id": session_id,
        },
    )

    return {
        "session_id": session_id,
        "message_id": str(agent_msg.id),
        "status": "sent",
        "role": "assistant",
    }


@router.post(
    "/chat/sessions/{session_id}/handover/suggest",
    summary="AI 生成建议回复 (Chat Session)",
)
async def handover_chat_suggest(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """AI 读取聊天会话上下文，生成建议回复"""
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问")

    # Load conversation history
    result = await db.execute(
        select(Conversation)
        .where(Conversation.session_id == session_id)
        .order_by(Conversation.created_at.asc())
        .limit(20)
    )
    rows = result.scalars().all()

    if not rows:
        return {"suggestions": ["暂无对话记录，无法生成建议"], "session_id": session_id}

    # Build conversation text
    conversation_text = "\n".join(
        f"{'客户' if r.role == 'user' else 'AI'}: {r.content}" for r in rows
    )

    try:
        from langchain_openai import ChatOpenAI
        from langchain.schema import SystemMessage, HumanMessage

        llm = ChatOpenAI(
            model=settings.default_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.7,
        )

        system_prompt = """你是丰田汽车销售主管，正在为人工客服提供回复建议。
根据对话上下文，生成2-3条可用的回复话术供客服选择。
每条话术应简洁、专业、有说服力，能有效推进销售。

以JSON数组格式返回: ["建议1", "建议2", "建议3"]"""

        user_prompt = f"""当前对话上下文：
{conversation_text[-2000:]}

请生成2-3条回复建议："""

        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        content = response.content if hasattr(response, "content") else str(response)

        import json as json_module
        try:
            suggestions = json_module.loads(content)
            if isinstance(suggestions, list) and all(isinstance(s, str) for s in suggestions):
                return {"suggestions": suggestions[:3], "session_id": session_id}
        except (json_module.JSONDecodeError, TypeError):
            pass

        # Fallback: extract lines
        lines = [l.strip().lstrip("0123456789.、- ") for l in content.split("\n") if l.strip() and len(l.strip()) > 5]
        return {"suggestions": lines[:3] or ["请根据对话继续沟通"], "session_id": session_id}

    except Exception as e:
        logger.warning(f"[Handover Suggest] LLM failed: {e}")
        return {"suggestions": ["了解客户需求并推荐合适车型", "强调丰田品质和保值率优势", "邀请客户到店试驾体验"], "session_id": session_id}


@router.get(
    "/chat/sessions/{session_id}/handover",
    summary="获取当前接管状态 (Chat Session)",
)
async def get_chat_handover_mode(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """查询聊天会话的当前接管模式"""
    state = await _get_or_create_session_state(db, session_id)
    return {"session_id": session_id, "handover_mode": state.handover_mode}
