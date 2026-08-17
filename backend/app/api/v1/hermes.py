"""
Hermes 内部助手代理路由 — 转发 CRMBOT → Hermes Agent (localhost:8642)

提供 OpenAI 兼容的代理接口，将对话请求转发到本地 Hermes 服务。
所有接口需要 admin 鉴权。
"""
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.auth import get_current_user

router = APIRouter(prefix="/hermes", tags=["hermes"])


# ── 请求模型 ──────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., description="消息角色：user / assistant / system")
    content: str = Field(..., description="消息内容")


class HermesChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., description="对话消息列表")


# ── 依赖：admin 鉴权 ──────────────────────────────────────

async def require_admin(current_user: Optional[dict] = Depends(get_current_user)):
    if current_user is None or current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


# ── 公共：转发请求到 Hermes ───────────────────────────────

def _hermes_headers() -> dict:
    """构建转发到 Hermes 的请求头"""
    headers = {"Content-Type": "application/json"}
    if settings.HERMES_API_KEY:
        headers["Authorization"] = f"Bearer {settings.HERMES_API_KEY}"
    return headers


def _build_hermes_body(messages: list[ChatMessage], stream: bool = False) -> dict:
    """构建 OpenAI 兼容的请求体"""
    return {
        "model": "hermes-agent",
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "stream": stream,
    }


# ── 端点 ──────────────────────────────────────────────────

@router.get("/health")
async def hermes_health(_admin: dict = Depends(require_admin)):
    """
    检测 Hermes 在线状态
    
    调用 Hermes /health 端点，返回 { online: bool }
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(f"{settings.HERMES_API_URL}/health")
            if resp.status_code == 200:
                return {"online": True}
            return {"online": False, "status_code": resp.status_code}
    except httpx.TimeoutException:
        return {"online": False, "detail": "Hermes 连接超时"}
    except Exception as e:
        return {"online": False, "detail": str(e)}


@router.post("/chat")
async def hermes_chat(
    body: HermesChatRequest,
    _admin: dict = Depends(require_admin),
):
    """
    非流式对话 — 转发到 Hermes Agent
    
    请求体: { "messages": [{"role":"user","content":"..."}] }
    超时: 30 秒
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                f"{settings.HERMES_API_URL}/chat/completions",
                json=_build_hermes_body(body.messages, stream=False),
                headers=_hermes_headers(),
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Hermes 响应超时")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code if e.response else 502,
            detail=f"Hermes 错误: {e}",
        )
    except HTTPException:
        raise  # 不二次包装 FastAPI 自己的异常
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Hermes 不可用: {str(e)}")


@router.post("/chat/stream")
async def hermes_chat_stream(
    body: HermesChatRequest,
    _admin: dict = Depends(require_admin),
):
    """
    流式对话 (SSE) — 转发到 Hermes Agent
    
    使用 StreamingResponse 逐块转发 SSE 事件
    """
    try:
        # 注意：不能使用 async with，因为 StreamingResponse 的 generator
        # 在函数返回后才被消费；async with 会提前关闭 client，导致流中断。
        client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        req = client.build_request(
            "POST",
            f"{settings.HERMES_API_URL}/chat/completions",
            json=_build_hermes_body(body.messages, stream=True),
            headers=_hermes_headers(),
        )
        resp = await client.send(req, stream=True)

        if resp.status_code >= 400:
            error_body = await resp.aread()
            await client.aclose()
            detail = error_body.decode("utf-8", errors="ignore")[:500]
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Hermes 错误: {detail}",
            )

        async def sse_generator():
            """逐行读取 Hermes SSE 流并转发"""
            try:
                async for chunk in resp.aiter_raw():
                    yield chunk
            except httpx.TransportError as e:
                yield f"data: [ERROR] 连接中断: {str(e)}\n\n".encode("utf-8")
            finally:
                await client.aclose()

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
            },
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Hermes 响应超时")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Hermes 不可用: {str(e)}")
