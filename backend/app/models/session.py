"""
聚合聊天会话模型 - sessions 表

用于管理聚合聊天（阶段二）中的会话生命周期：
- 一个 Session 可关联多条 Conversation 记录
- 支持状态流转: new → active → negotiating → closed / lost
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.tenant import TenantMixin


class Session(TenantMixin, Base):
    """聚合聊天会话表"""
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="会话唯一标识 (UUID)"
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="会话标题"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="new",
        comment="会话状态: new / active / negotiating / closed / lost"
    )
    customer_name: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="客户名称"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        comment="最后更新时间"
    )
    handover_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ai",
        comment="接管模式: ai / human"
    )
    handover_suggestion: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="AI 生成的建议回复（人工模式下使用）"
    )

    def __repr__(self):
        return (
            f"<Session(id={self.id}, title='{self.title}', "
            f"status='{self.status}', customer='{self.customer_name}')>"
        )
