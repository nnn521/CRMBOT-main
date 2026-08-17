"""Authenticated access to documents generated in customer conversations."""

import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.chat import DocumentInfo, DocumentType
from app.models.conversation import Conversation
from app.models.db import get_db
from app.services.auth import get_current_user

logger = get_logger("api.documents")
router = APIRouter()

MIME_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}
DOCUMENT_TYPES = {
    ".docx": DocumentType.DOCX,
    ".xlsx": DocumentType.XLSX,
    ".pptx": DocumentType.PPTX,
    ".pdf": DocumentType.PDF,
}


def _validate_filename(filename: str) -> None:
    """Reject traversal and platform-specific path separators before file access."""
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件名")


def _document_names_from_metadata(metadata: Optional[dict]) -> set[str]:
    """Extract generated filenames from persisted assistant-message metadata."""
    if not isinstance(metadata, dict):
        return set()
    documents = metadata.get("documents", [])
    if not isinstance(documents, list):
        return set()
    return {
        item.get("file_name")
        for item in documents
        if isinstance(item, dict) and isinstance(item.get("file_name"), str)
    }


async def _owned_document_names(db: AsyncSession, user_id: int) -> set[str]:
    result = await db.execute(
        select(Conversation.metadata_json).where(
            Conversation.user_open_id == str(user_id),
            Conversation.role == "assistant",
        )
    )
    names: set[str] = set()
    for metadata in result.scalars().all():
        names.update(_document_names_from_metadata(metadata))
    return names


def _require_user(current_user: Optional[dict]) -> dict:
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return current_user


async def _assert_document_access(
    filename: str, db: AsyncSession, current_user: Optional[dict]
) -> dict:
    user = _require_user(current_user)
    if user.get("role") == "admin":
        return user
    if filename not in await _owned_document_names(db, user["user_id"]):
        # Do not reveal whether another user's document exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    return user


def _safe_document_path(filename: str) -> str:
    _validate_filename(filename)
    output_dir = os.path.realpath(settings.output_dir)
    file_path = os.path.realpath(os.path.join(output_dir, filename))
    if os.path.commonpath([output_dir, file_path]) != output_dir:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件名")
    return file_path


@router.get("/documents/{filename}", summary="下载已授权的生成文档")
async def download_document(
    filename: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user),
):
    await _assert_document_access(filename, db, current_user)
    file_path = _safe_document_path(filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    extension = Path(filename).suffix.lower()
    logger.info("document_download filename=%s user_id=%s", filename, current_user["user_id"])
    return FileResponse(file_path, filename=filename, media_type=MIME_TYPES.get(extension, "application/octet-stream"))


@router.get("/documents", response_model=list[DocumentInfo], summary="列出已授权的生成文档")
async def list_documents(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user),
) -> List[DocumentInfo]:
    user = _require_user(current_user)
    output_dir = os.path.realpath(settings.output_dir)
    if not os.path.isdir(output_dir):
        return []

    allowed_names: Optional[set[str]] = None
    if user.get("role") != "admin":
        allowed_names = await _owned_document_names(db, user["user_id"])

    files = sorted(
        (
            item for item in os.listdir(output_dir)
            if os.path.isfile(os.path.join(output_dir, item))
            and (allowed_names is None or item in allowed_names)
        ),
        key=lambda item: os.path.getmtime(os.path.join(output_dir, item)),
        reverse=True,
    )[offset:offset + limit]

    return [
        DocumentInfo(
            doc_type=DOCUMENT_TYPES.get(Path(filename).suffix.lower(), DocumentType.DOCX),
            file_name=filename,
            file_path=f"/api/v1/documents/{filename}",
            file_size=os.path.getsize(os.path.join(output_dir, filename)),
        )
        for filename in files
    ]


@router.delete("/documents/{filename}", summary="删除生成文档（仅管理员）")
async def delete_document(
    filename: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user),
):
    user = _require_user(current_user)
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可删除文档")
    file_path = _safe_document_path(filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    os.remove(file_path)
    logger.info("document_deleted filename=%s admin_id=%s", filename, user["user_id"])
    return {"status": "deleted", "filename": filename}
