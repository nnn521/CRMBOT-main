"""
对话记录模型 - 持久化存储聊天历史

与 LangGraph checkpointer 互补：
- checkpointer: 存储 Agent 工作流状态（短期）
- Conversation: 存储完整对话记录（长期，可查询）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.db import Base
from app.models.tenant import TenantMixin


class Conversation(TenantMixin, Base):
    """对话记录表"""
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True, comment="会话ID"
    )
    user_open_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True, comment="用户 openid"
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="消息角色: user/assistant/system"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="消息内容"
    )
    intent: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="识别到的意图"
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="附加元数据"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="消息时间"
    )

    def __repr__(self):
        return f"<Conversation(id={self.id}, session={self.session_id}, role={self.role})>"
