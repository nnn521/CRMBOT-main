"""
Auth API — 注册 / 登录 / 当前用户
"""
from datetime import datetime
import asyncio

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.auth import UserCreate, UserLogin, TokenResponse, UserResponse
from app.services.auth import (
    create_user,
    authenticate_user,
    create_access_token,
    get_current_user,
    init_users_table,
)
from app.services.rate_limiter import enforce_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

# 标记为需要在 startup 时初始化
_initialized = False
_init_lock = asyncio.Lock()


async def ensure_users_table():
    global _initialized
    if _initialized:
        return
    async with _init_lock:
        if _initialized:
            return
        await init_users_table()
        if settings.bootstrap_admin_username and settings.bootstrap_admin_password:
            try:
                await create_user(
                    settings.bootstrap_admin_username,
                    settings.bootstrap_admin_password,
                    "admin",
                )
            except IntegrityError:
                pass
        _initialized = True


@router.post("/register", response_model=TokenResponse)
async def register(data: UserCreate, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(
        f"auth:{client_ip}",
        limit=settings.auth_rate_limit,
        window_seconds=settings.rate_limit_window_seconds,
    )
    try:
        await ensure_users_table()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="认证数据库不可用")
    try:
        uid = await create_user(data.username, data.password, data.role)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="用户名已存在")
    except RuntimeError:
        raise HTTPException(status_code=503, detail="认证数据库不可用")

    token = create_access_token(
        {"sub": str(uid), "username": data.username, "role": data.role}
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=uid,
            username=data.username,
            role=data.role,
            created_at=datetime.now(),
        ),
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(
        f"auth:{client_ip}",
        limit=settings.auth_rate_limit,
        window_seconds=settings.rate_limit_window_seconds,
    )
    try:
        await ensure_users_table()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="认证数据库不可用")
    user = await authenticate_user(data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(
        {"sub": str(user["id"]), "username": user["username"], "role": user["role"]}
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user["id"],
            username=user["username"],
            role=user["role"],
            created_at=datetime.now(),
        ),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户信息"""
    if current_user is None:
        raise HTTPException(status_code=401, detail="未登录")
    return UserResponse(
        id=current_user["user_id"],
        username=current_user["username"],
        role=current_user["role"],
        created_at=datetime.now(),
    )
