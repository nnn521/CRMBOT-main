"""
Auth API — 注册 / 登录 / 登出 / 当前用户

认证方式：JWT 通过 httpOnly Cookie 下发（同时兼容 Authorization: Bearer 头）。
前端不再把 token 存 localStorage，避免 XSS 窃取。
"""
from datetime import datetime
import asyncio

from fastapi import APIRouter, HTTPException, Depends, Request, Response
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.logging import get_logger
from app.models.auth import UserCreate, UserLogin, TokenResponse, UserResponse
from app.services.auth import (
    create_user,
    authenticate_user,
    create_access_token,
    get_current_user,
    init_users_table,
    build_auth_cookie,
    revoke_all_tokens,
)
from app.services.rate_limiter import enforce_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger("api.auth")

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
            except ValueError:
                # 密码超过 bcrypt 72 字节上限等配置错误：记录后继续启动，
                # 不因 bootstrap 账号失败阻塞整个服务（管理员可手工修正配置）。
                logger.error(
                    "bootstrap admin 创建失败：BOOTSTRAP_ADMIN_PASSWORD 不合法"
                    "（bcrypt 上限 72 字节），已跳过"
                )
        _initialized = True


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _enforce_auth_limits(request: Request, username: str):
    """IP 级 + 用户名级双重限流，防暴力破解（代理后 IP 相同也有用户名维度）。"""
    ip = _client_ip(request)
    await enforce_rate_limit(
        f"auth:{ip}",
        limit=settings.auth_rate_limit,
        window_seconds=settings.rate_limit_window_seconds,
    )
    await enforce_rate_limit(
        f"auth-user:{username.lower()}",
        limit=5,
        window_seconds=60,
    )


def _issue_token(response: Response, user: dict) -> TokenResponse:
    token = create_access_token(
        {
            "sub": str(user["id"]),
            "username": user["username"],
            "role": user["role"],
            "ver": user.get("token_version", 0),
        }
    )
    response.set_cookie(**build_auth_cookie(token))
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


@router.post("/register", response_model=TokenResponse)
async def register(data: UserCreate, request: Request, response: Response):
    await _enforce_auth_limits(request, data.username)
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

    user = {"id": uid, "username": data.username, "role": data.role, "token_version": 0}
    return _issue_token(response, user)


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, request: Request, response: Response):
    await _enforce_auth_limits(request, data.username)
    try:
        await ensure_users_table()
    except RuntimeError:
        raise HTTPException(status_code=503, detail="认证数据库不可用")
    user = await authenticate_user(data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    return _issue_token(response, user)


@router.post("/logout")
async def logout(
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    """登出：吊销该用户全部已签发令牌并清除 Cookie。"""
    try:
        await revoke_all_tokens(current_user["user_id"])
    except RuntimeError:
        pass  # 数据库不可用时仍清除客户端 Cookie
    response.delete_cookie(build_auth_cookie("")["key"], path="/")
    return {"status": "logged_out"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserResponse(
        id=current_user["user_id"],
        username=current_user["username"],
        role=current_user["role"],
        created_at=datetime.now(),
    )
