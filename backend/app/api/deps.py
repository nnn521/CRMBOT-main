"""
API 依赖模块 - 处理认证、数据库会话等
"""

import hmac
from typing import Generator, Optional

from fastapi import Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("api.deps")

# 微信小程序 JWT Token 认证（预留）
security = HTTPBearer(auto_error=False)


async def verify_wechat_token(
    authorization: Optional[str] = Header(None, description="微信小程序登录凭证")
) -> str:
    """
    验证微信小程序 Token
    
    实际项目中，这里需要：
    1. 解析 JWT token
    2. 验证 token 有效性
    3. 返回用户 openid
    
    当前简化实现：直接返回 session_id
    """
    # TODO: 实现真正的微信 Token 验证
    # 暂时直接返回，用于开发测试
    if authorization and authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "")
    return "anonymous"


async def get_current_session(
    x_session_id: Optional[str] = Header(None, description="会话ID")
) -> str:
    """
    获取当前会话ID
    
    优先从 Header 获取，否则生成临时会话ID
    """
    if x_session_id:
        return x_session_id
    
    import uuid
    return f"temp_{uuid.uuid4().hex[:8]}"


def get_api_key(
    x_api_key: Optional[str] = Header(None, description="API Key")
) -> str:
    """
    验证 API Key（用于服务端间调用）
    """
    if not settings.internal_api_key:
        logger.error("拒绝服务间请求：未配置 INTERNAL_API_KEY")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="服务间认证未配置",
        )
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.internal_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 无效")
    return x_api_key
