"""Customer lead capture and satisfaction feedback endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.engagement import Lead, SatisfactionFeedback
from app.services.auth import get_current_user
from app.services.rate_limiter import enforce_rate_limit
from app.api.v1.chat import _assert_session_owner


router = APIRouter(tags=["customer engagement"])


class LeadCreate(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=64)
    phone: str = Field(pattern=r"^1[3-9]\d{9}$")
    car_model: Optional[str] = Field(None, max_length=128)
    budget_range: Optional[str] = Field(None, max_length=64)
    purchase_time: Optional[str] = Field(None, max_length=64)
    notes: Optional[str] = Field(None, max_length=1000)


class FeedbackCreate(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    rating: int = Field(ge=1, le=5)
    speed: int = Field(ge=1, le=4)
    professionalism: int = Field(ge=1, le=4)
    comment: Optional[str] = Field(None, max_length=1000)
    would_recommend: bool


def _require_user(current_user: Optional[dict]) -> dict:
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return current_user


async def _guard_engagement(db: AsyncSession, current_user: dict, session_id: str) -> None:
    """线索/反馈只能提交到自己拥有的会话；并按用户限流防止刷单。"""
    await _assert_session_owner(db, session_id, current_user)
    await enforce_rate_limit(
        f"engagement:{current_user['user_id']}",
        limit=10,
        window_seconds=60,
    )


@router.post("/leads", status_code=status.HTTP_201_CREATED)
async def create_lead(
    body: LeadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user),
):
    user = _require_user(current_user)
    await _guard_engagement(db, user, body.session_id)
    lead = Lead(user_id=user["user_id"], **body.model_dump())
    db.add(lead)
    await db.flush()
    return {"id": lead.id, "coupon_code": f"CRM{lead.id:06d}"}


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def create_feedback(
    body: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user),
):
    user = _require_user(current_user)
    await _guard_engagement(db, user, body.session_id)
    feedback = SatisfactionFeedback(user_id=user["user_id"], **body.model_dump())
    db.add(feedback)
    await db.flush()
    return {"id": feedback.id, "status": "recorded"}
