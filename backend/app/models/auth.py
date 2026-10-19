"""
认证相关 Pydantic 模型 — JWT auth (admin/customer roles)
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["customer"] = "customer"

    @field_validator("password")
    @classmethod
    def password_within_bcrypt_limit(cls, v: str) -> str:
        """bcrypt 只使用前 72 字节：超过会静默截断，导致不同密码哈希相同。"""
        if len(v.encode("utf-8")) > 72:
            raise ValueError("密码过长：bcrypt 仅支持 72 字节（UTF-8）以内的密码")
        return v


class UserLogin(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
