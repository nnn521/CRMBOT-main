"""
聊天会话运行时状态模型

独立轻量表，不关联 sessions / conversations。
session_id 直接使用 conversations.session_id 的字符串值。
"""
from sqlalchemy import Column, String, Boolean, DateTime
from app.models.db import Base
from datetime import datetime, timezone


class ChatSessionState(Base):
    __tablename__ = "chat_session_state"

    session_id = Column(String(255), primary_key=True, comment="会话ID（对应 conversations.session_id）")
    handover_mode = Column(String(10), nullable=False, default="ai", comment="接管模式: ai / human")
    high_intent_alerted = Column(Boolean, nullable=False, default=False, comment="是否已触发高意向提醒")
    status = Column(String(20), nullable=False, default="active", comment="会话状态: new/active/closed")
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), comment="最后更新时间")
