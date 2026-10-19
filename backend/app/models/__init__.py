"""
数据模型统一导出

包含：
- Pydantic 模型（API 请求/响应）
- SQLAlchemy 模型（数据库持久化）
"""

# Pydantic 模型（API 层）
from app.models.chat import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    DocumentInfo,
    DocumentType,
    IntentAnalysisResult,
    MessageRole,
    UserIntent,
    QuoteParams,
    ProposalParams,
    ContractParams,
    AnalysisParams,
    PresentationParams,
)

# SQLAlchemy 模型（数据库层）
from app.models.user import User
from app.models.conversation import Conversation
from app.models.config import SystemConfig
from app.models.chat_session_state import ChatSessionState
from app.models.account import AuthAccount
from app.models.engagement import Lead, SatisfactionFeedback

__all__ = [
    # Pydantic
    "ChatMessage", "ChatRequest", "ChatResponse",
    "DocumentInfo", "DocumentType", "IntentAnalysisResult",
    "MessageRole", "UserIntent",
    "QuoteParams", "ProposalParams", "ContractParams",
    "AnalysisParams", "PresentationParams",
    # SQLAlchemy
    "User", "Conversation", "SystemConfig", "ChatSessionState",
    "AuthAccount",
    "Lead", "SatisfactionFeedback",
]
