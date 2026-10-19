"""
API 依赖模块 - 处理会话 ID 解析等
"""

from typing import Optional

from fastapi import Header


async def get_current_session(
    x_session_id: Optional[str] = Header(None, description="会话ID")
) -> str:
    """
    获取当前会话ID

    优先从 Header 获取，否则生成临时会话ID。
    """
    if x_session_id:
        return x_session_id

    import uuid
    return f"temp_{uuid.uuid4().hex[:8]}"
