from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.ws_manager import manager
from app.services.auth import SECRET_KEY, ALGORITHM
from app.models.conversation import Conversation
from app.models.db import async_session_factory
from sqlalchemy import select
from jose import JWTError, jwt
import json
import logging
from datetime import datetime, timezone

router = APIRouter()
logger = logging.getLogger(__name__)


async def _decode_ws_user(websocket: WebSocket) -> dict | None:
    """验证 WebSocket 连接的 JWT（httpOnly Cookie，随握手自动携带）。

    安全修复：JWT 不再通过 URL query 传输（会泄露到代理/访问日志）。
    """
    token = websocket.cookies.get("crmbot_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload if payload.get("sub") is not None else None
    except JWTError:
        return None


async def _can_watch_session(user: dict, session_id: str) -> bool:
    """Authorize a WebSocket subscription with the same ownership rule as chat."""
    if user.get("role") == "admin":
        return True
    username = user.get("username", "")
    if session_id == f"session_{username}":
        return True
    if async_session_factory is None:
        return False
    async with async_session_factory() as db:
        result = await db.execute(
            select(Conversation.id).where(
                Conversation.session_id == session_id,
                Conversation.user_open_id == str(user["sub"]),
                Conversation.role == "user",
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    # 鉴权检查
    user = await _decode_ws_user(websocket)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    if session_id == "admin" and user.get("role") != "admin":
        await websocket.close(code=4003, reason="Forbidden")
        return
    if session_id != "admin" and not await _can_watch_session(user, session_id):
        await websocket.close(code=4003, reason="Forbidden")
        return

    # 连接与首条消息放入 try：客户端在 accept 与首条消息之间断开时也能清理
    try:
        await manager.connect(websocket, session_id)
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("[WS] connected channel=%s user=%s", session_id, user.get("username"))
        while True:
            data = await websocket.receive_text()
            # Client can send keepalive messages
            message = json.loads(data)
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
    except Exception as exc:
        logger.warning("[WS] channel=%s disconnected with error: %s", session_id, exc)
        manager.disconnect(websocket, session_id)
