"""Authenticated shared-corpus reads and explicit administrator publication."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from psycopg import IntegrityError
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.config import settings
from app.services.auth import get_current_user
from app.services.knowledge.runtime import (
    KnowledgeNotFound, KnowledgeRuntime, open_knowledge_runtime,
)
from app.services.knowledge.storage import StorageConflict


router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=[Depends(get_current_user)])
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
VehicleModel = Literal["CAMRY", "HIGHLANDER", "RAV4"]
Powertrain = Literal[
    "2.0", "2.5", "燃油", "双擎", "插混",
    "2.0 燃油", "2.0 双擎", "2.0 插混", "2.5 燃油", "2.5 双擎", "2.5 插混",
]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StatusInfo(Schema):
    enabled: bool
    ready: bool
    release_id: str | None = None
    embedding_compatible: bool = False
    scope: Literal["shared_authenticated"] = "shared_authenticated"


class CitationInfo(Schema):
    citation_id: str
    span_id: str
    source_id: str
    document_version: str
    title: str
    locator: dict
    quote: str
    url: str


class SourceCreate(Schema):
    doc_id: Identifier
    source_uri: str = Field(min_length=1, max_length=1000, pattern=r"^[^\x00-\x1f]+$")


class SourceInfo(Schema):
    source_id: str
    doc_id: str


class UploadInfo(Schema):
    source_id: str
    version_id: str
    span_count: int


class BuildCreate(Schema):
    version_ids: list[Digest] = Field(min_length=1, max_length=100)
    idempotency_key: Identifier


class BuildInfo(Schema):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    attempts: int
    error: str | None = None
    release_id: str | None = None
    release_status: str | None = None


class RevokeRequest(Schema):
    reason: str = Field(min_length=1, max_length=500, pattern=r"^[^\x00]+$")


class PublishInfo(Schema):
    release_id: str
    status: Literal["published"]


class RevocationInfo(Schema):
    source_id: str
    revoked: bool


class SearchHit(Schema):
    score: float
    citation: CitationInfo


class SearchInfo(Schema):
    release_id: str
    hits: list[SearchHit]
    mode: Literal["source_quotes_only"] = "source_quotes_only"
    degraded: list[str] = Field(default_factory=list)


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


async def get_runtime():
    try:
        async with open_knowledge_runtime() as runtime:
            yield runtime
    except (HTTPException, RequestValidationError):
        raise
    except KnowledgeNotFound:
        raise HTTPException(status_code=404, detail="知识来源或引用不可用") from None
    except (StorageConflict, IntegrityError):
        raise HTTPException(status_code=409, detail="知识记录冲突或构建尚未完成") from None
    except ValueError:
        raise HTTPException(status_code=422, detail="知识请求或文档内容不符合约束") from None
    except Exception:
        # Never return psycopg/provider exception strings (DSN, headers, keys).
        raise HTTPException(status_code=503, detail="知识服务暂不可用") from None


async def readiness() -> dict:
    """Health probe only: no migration, worker, model call or secret in output."""
    if not settings.rag_v2_enabled:
        return {"enabled": False, "ready": True, "status": "disabled"}
    try:
        async with open_knowledge_runtime() as runtime:
            info = await runtime.status()
        return {"enabled": True, "ready": info["ready"],
                "status": "ready" if info["ready"] else "unavailable"}
    except Exception:
        return {"enabled": True, "ready": False, "status": "unavailable"}


def _citation_info(row: dict) -> CitationInfo:
    identity = json.dumps(["citation-v1", row["span_id"], row["original_text"]], ensure_ascii=False,
                          separators=(",", ":"))
    return CitationInfo(citation_id="cite-" + sha256(identity.encode("utf-8")).hexdigest(),
        span_id=row["span_id"], source_id=row["source_id"], document_version=row["version_id"],
        title=row["title"], locator=row["locator"], quote=row["original_text"],
        url=f"{settings.api_v1_prefix}/knowledge/releases/{row['release_id']}/citations/{row['span_id']}")


@router.get("/status", response_model=StatusInfo)
async def status():
    if not settings.rag_v2_enabled:
        return StatusInfo(enabled=False, ready=False)
    try:
        async with open_knowledge_runtime() as runtime:
            return await runtime.status()
    except Exception:
        raise HTTPException(status_code=503, detail="知识服务暂不可用") from None


@router.get("/releases/{release_id}/citations/{span_id}", response_model=CitationInfo)
async def citation(release_id: Identifier, span_id: Digest, runtime: KnowledgeRuntime = Depends(get_runtime)):
    return _citation_info(await runtime.citation(release_id, span_id))


@router.get("/search", response_model=SearchInfo)
async def search(q: Annotated[str, Field(min_length=1, max_length=2000)],
                 top_k: Annotated[int, Field(ge=1, le=20)] = 5,
                 runtime: KnowledgeRuntime = Depends(get_runtime)):
    result = await runtime.search(q, top_k=top_k)
    # Citation lookup performs one last live revocation check; a race fails the
    # whole response closed rather than emitting an earlier candidate snapshot.
    hits = [SearchHit(score=item.score, citation=_citation_info(
        await runtime.citation(result.release_id, item.evidence.span_id))) for item in result.ranked]
    return SearchInfo(release_id=result.release_id, hits=hits, degraded=list(result.degraded))


@router.get("/sources", dependencies=[Depends(require_admin)])
async def sources(runtime: KnowledgeRuntime = Depends(get_runtime)):
    return {"sources": await runtime.list_sources()}


@router.post("/sources", response_model=SourceInfo, status_code=201, dependencies=[Depends(require_admin)])
async def create_source(data: SourceCreate, runtime: KnowledgeRuntime = Depends(get_runtime)):
    return await runtime.create_source(doc_id=data.doc_id, source_uri=data.source_uri)


@router.post("/sources/{source_id}/versions", response_model=UploadInfo, status_code=201,
             dependencies=[Depends(require_admin)])
async def upload(source_id: Identifier, request: Request,
                 title: Annotated[str, Field(min_length=1, max_length=200)] = "Markdown 来源",
                 vehicle_model: VehicleModel | None = None,
                 model_year: Annotated[int | None, Field(ge=2000, le=2099)] = None,
                 powertrain: Powertrain | None = None,
                 runtime: KnowledgeRuntime = Depends(get_runtime)):
    # Ambiguous scope is rejected rather than silently dropped or guessed.
    if any(len(request.query_params.getlist(name)) > 1 for name in
           ("title", "vehicle_model", "model_year", "powertrain")):
        raise HTTPException(status_code=422, detail="上传参数不能重复")
    if vehicle_model is None and (model_year is not None or powertrain is not None):
        raise HTTPException(status_code=422, detail="指定年款或动力时必须同时指定车型")
    # Raw text body, not a path/URL/fetch or unconstrained multipart file. Bound
    # the streamed bytes as well as Content-Length (which is untrusted).
    content_type = request.headers.get("content-type", "").lower().replace(" ", "")
    parts = content_type.split(";")
    if parts[0] not in {"text/plain", "text/markdown"} or any(p != "charset=utf-8" for p in parts[1:]):
        raise HTTPException(status_code=415, detail="仅接受 UTF-8 text/plain 或 text/markdown")
    limit = runtime.config.knowledge_upload_max_bytes
    content = bytearray()
    async for block in request.stream():
        if len(content) + len(block) > limit:
            raise HTTPException(status_code=413, detail="上传文档超过大小限制")
        content.extend(block)
    # Missing model has no applicable vehicle scope. Never infer it from title,
    # filename or text; null year/power remain explicitly unspecified.
    metadata = {"vehicle_scopes": [
        {"model": vehicle_model, "year": model_year, "powertrain": powertrain}
    ] if vehicle_model is not None else []}
    return await runtime.upload(source_id, bytes(content), title=title, metadata=metadata)


@router.post("/builds", response_model=BuildInfo, status_code=202)
async def enqueue_build(data: BuildCreate, user: dict = Depends(require_admin),
                        runtime: KnowledgeRuntime = Depends(get_runtime)):
    return await runtime.enqueue_build(data.version_ids, idempotency_key=data.idempotency_key,
                                       requested_by=str(user["user_id"]))


@router.get("/builds/{job_id}", response_model=BuildInfo, dependencies=[Depends(require_admin)])
async def build_status(job_id: UUID, runtime: KnowledgeRuntime = Depends(get_runtime)):
    return await runtime.build_status(job_id)


@router.post("/releases/{release_id}/publish", response_model=PublishInfo,
             dependencies=[Depends(require_admin)])
async def publish(release_id: Identifier, runtime: KnowledgeRuntime = Depends(get_runtime)):
    return await runtime.publish(release_id)


@router.post("/sources/{source_id}/revoke", response_model=RevocationInfo)
async def revoke(source_id: Identifier, data: RevokeRequest, user: dict = Depends(require_admin),
                 runtime: KnowledgeRuntime = Depends(get_runtime)):
    return await runtime.revoke(source_id, reason=data.reason, revoked_by=str(user["user_id"]))
