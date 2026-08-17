"""
认证服务 — JWT 签发 / 密码哈希 / 用户 CRUD
"""
import asyncio
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select

from app.core.config import settings
from app.models.account import AuthAccount
from app.models.db import async_session_factory, engine

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# Issue #10: 必须配置 SECRET_KEY，不允许随机生成（会导致旧 token 全部失效）
SECRET_KEY = settings.secret_key
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY 未配置，请在 .env 中设置 SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def _require_database():
    if engine is None or async_session_factory is None:
        raise RuntimeError("认证功能需要配置 PostgreSQL DATABASE_URL")


async def init_users_table():
    """Ensure the authentication table exists."""
    _require_database()
    async with engine.begin() as conn:
        await conn.run_sync(AuthAccount.__table__.create, checkfirst=True)


async def create_user(username: str, password: str, role: str = "customer") -> int:
    """创建新用户，返回 user_id"""
    _require_database()
    async with async_session_factory() as session:
        account = AuthAccount(
            username=username,
            password_hash=await asyncio.to_thread(pwd_context.hash, password),
            role=role,
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
        pwd_context.verify, password, account.password_hash
    ):
        return None
    return {"id": account.id, "username": account.username, "role": account.role}


def create_access_token(data: dict) -> str:
    """生成 JWT access token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict | None:
    """
    从 Bearer token 解码当前用户。
    未传 token 时返回 None（允许可选鉴权），token 无效时返回 None。
    """
    if credentials is None:
        return None
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        username = payload.get("username")
        role = payload.get("role")
        if user_id is None:
            return None
        return {"user_id": int(user_id), "username": username, "role": role}
    except JWTError:
        return None
