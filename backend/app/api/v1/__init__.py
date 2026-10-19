from app.api.v1.chat import router as chat_router
from app.api.v1.documents import router as documents_router
from app.api.v1.images import router as images_router
from app.api.v1.ws import router as ws_router
from app.api.v1.auth import router as auth_router
from app.api.v1.reports import router as reports_router
from app.api.v1.hermes import router as hermes_router
from app.api.v1.engagement import router as engagement_router

__all__ = [
    "chat_router",
    "documents_router",
    "images_router",
    "ws_router",
    "auth_router",
    "reports_router",
    "hermes_router",
    "engagement_router",
]
