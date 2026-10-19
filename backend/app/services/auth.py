"""
认证服务 — JWT 签发 / 密码哈希 / 用户 CRUD / 令牌吊销

安全基线：
- SECRET_KEY 必须是强随机值：拒绝占位符与过短密钥（否则任何人都能伪造 JWT）
- JWT 内嵌 token_version：登出/改密时 +1，旧令牌立即失效
- get_current_user 统一抛出 401（不再返回 None 造成 403/401 混用）
- 支持 httpOnly Cookie 认证（前端不再把 JWT 存 localStorage）
"""
import asyncio
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, text, update

from app.core.config import settings
from app.models.account import AuthAccount
from app.models.db import async_session_factory, engine

security = HTTPBearer(auto_error=False)

AUTH_COOKIE_NAME = "crmbot_token"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# 已知占位密钥：绝不允许作为 SECRET_KEY 使用
_FORBIDDEN_SECRETS = {
    "",
    "replace-with-a-random-secret",
    "replace-with-a-second-random-secret",
    "changeme",
    "change-me",
    "secret",
    "secretkey",
    "your-secret-key",
    "your_secret_key",
}

def _validate_secret(secret: str) -> None:
    """拒绝占位/过短密钥，否则任何人都能伪造 JWT。"""
    if secret in _FORBIDDEN_SECRETS or len(secret) < 32:
        raise RuntimeError(
            "SECRET_KEY 未配置或为占位值/过短（至少 32 字符）。"
            "请使用 `openssl rand -hex 32` 生成强随机密钥并写入 .env"
        )


SECRET_KEY = settings.secret_key
_validate_secret(SECRET_KEY)


def _require_database():
    if engine is None or async_session_factory is None:
        raise RuntimeError("认证功能需要配置 PostgreSQL DATABASE_URL")


# ═══════════════════════════════════════════════════════════════
# 密码哈希（bcrypt 原生 API）
# ═══════════════════════════════════════════════════════════════
# 不使用 passlib：passlib 1.7.4 的后端探测会调用 bcrypt 已移除的
# `__about__`，在 bcrypt>=4.1 上直接抛 ValueError，导致注册/登录 500。
# 原生 API 生成的 `$2b$` 哈希与历史 passlib 数据完全兼容。

BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """生成 bcrypt 哈希（返回 str，便于直接写入数据库）。"""
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise ValueError("密码过长：bcrypt 仅支持 72 字节（UTF-8）以内的密码")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码；哈希损坏或密码超长时返回 False，绝不抛异常。"""
    try:
        encoded = password.encode("utf-8")
        if len(encoded) > BCRYPT_MAX_BYTES:
            return False
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except (ValueError, TypeError, UnicodeEncodeError):
        return False


async def init_users_table():
    """Ensure the authentication table exists (including token_version column)."""
    _require_database()
    async with engine.begin() as conn:
        await conn.run_sync(AuthAccount.__table__.create, checkfirst=True)
        # 老库兼容迁移：补充 token_version 列（create_all 不会修改已有表）
        await conn.execute(
            text(
                "ALTER TABLE users_auth ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0"
            )
        )


async def create_user(username: str, password: str, role: str = "customer") -> int:
    """创建新用户，返回 user_id"""
    _require_database()
    async with async_session_factory() as session:
        account = AuthAccount(
            username=username,
            password_hash=await asyncio.to_thread(hash_password, password),
            role=role,
            token_version=0,
        )
        session.add(account)
        try:
            await session.commit()
            await session.refresh(account)
        except Exception:
            await session.rollback()
            raise
        return account.id


async def authenticate_user(username: str, password: str) -> dict | None:
    """验证用户名密码，成功返回用户信息字典，失败返回 None"""
    _require_database()
    async with async_session_factory() as session:
        result = await session.execute(
            select(AuthAccount).where(AuthAccount.username == username)
        )
        account = result.scalar_one_or_none()

    if not account or not await asyncio.to_thread(
        verify_password, password, account.password_hash
    ):
        return None
    return {
        "id": account.id,
        "username": account.username,
        "role": account.role,
        "token_version": account.token_version,
    }


def create_access_token(data: dict) -> str:
    """生成 JWT access token（内嵌 token_version 用于吊销）"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def build_auth_cookie(token: str) -> dict:
    """构造 httpOnly 认证 Cookie 参数（前端不再落 localStorage）。"""
    return {
        "key": AUTH_COOKIE_NAME,
        "value": token,
        "httponly": True,
        "samesite": "lax",
        "secure": settings.environment == "production",
        "max_age": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "path": "/",
    }


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    从 Bearer 头或 httpOnly Cookie 解析当前用户。

    统一语义：缺失/无效/已吊销的令牌一律 401（带 WWW-Authenticate），
    不再返回 None 导致不同端点混用 401/403。
    """
    token: str | None = None
    if credentials is not None:
        token = credentials.credentials
    else:
        token = request.cookies.get(AUTH_COOKIE_NAME)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_raw = payload.get("sub")
    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的登录凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if async_session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证服务不可用",
        )

    async with async_session_factory() as session:
        result = await session.execute(
            select(AuthAccount.token_version, AuthAccount.username, AuthAccount.role)
            .where(AuthAccount.id == user_id)
        )
        row = result.one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db_version, username, role = row
    if db_version != payload.get("ver"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已失效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"user_id": user_id, "username": username or payload.get("username"), "role": role or payload.get("role")}


async def revoke_all_tokens(user_id: int) -> bool:
    """登出：token_version +1，使该用户所有已签发令牌失效。"""
    _require_database()
    async with async_session_factory() as session:
        result = await session.execute(
            update(AuthAccount)
            .where(AuthAccount.id == user_id)
            .values(token_version=AuthAccount.token_version + 1)
        )
        await session.commit()
        return result.rowcount > 0
