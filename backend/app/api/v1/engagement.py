"""Customer lead capture and satisfaction feedback endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.engagement import Lead, SatisfactionFeedback
from app.services.auth import get_current_user


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


@router.post("/leads", status_code=status.HTTP_201_CREATED)
async def create_lead(
    body: LeadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user),
):
    user = _require_user(current_user)
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
    feedback = SatisfactionFeedback(user_id=user["user_id"], **body.model_dump())
    db.add(feedback)
    await db.flush()
    return {"id": feedback.id, "status": "recorded"}
