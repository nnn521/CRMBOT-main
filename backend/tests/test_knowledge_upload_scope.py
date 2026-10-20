"""Upload vehicle-scope query validation and metadata contract (fake runtime, no DB)."""

from contextlib import asynccontextmanager
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import knowledge as api
from app.services.auth import get_current_user


class FakeRuntime:
    def __init__(self):
        self.calls = []
        self.config = type("Config", (), {"knowledge_upload_max_bytes": 1000})()

    async def upload(self, source_id, content, *, title, metadata):
        self.calls.append((source_id, content, title, metadata))
        return {"source_id": source_id, "version_id": "a" * 64, "span_count": 1}


def client_for(runtime):
    @asynccontextmanager
    async def opened():
        yield runtime

    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": 1, "role": "admin", "username": "admin"}
    app.dependency_overrides[api.get_runtime] = lambda: runtime
    app.dependency_overrides[api.open_knowledge_runtime] = opened
    return TestClient(app)


@pytest.mark.parametrize("query,metadata", [
    ("vehicle_model=CAMRY", {"vehicle_scopes": [{"model": "CAMRY", "year": None, "powertrain": None}]}),
    ("vehicle_model=HIGHLANDER&model_year=2024&powertrain=2.5%20%E5%8F%8C%E6%93%8E",
     {"vehicle_scopes": [{"model": "HIGHLANDER", "year": 2024, "powertrain": "2.5 双擎"}]}),
    ("", {"vehicle_scopes": []}),
])
def test_upload_forwards_exact_scope_metadata(query, metadata):
    runtime = FakeRuntime()
    with client_for(runtime) as client:
        response = client.post(
            "/api/v1/knowledge/sources/src/versions" + (f"?{query}" if query else ""),
            content="# 原文\n内容。\n".encode(), headers={"Content-Type": "text/markdown; charset=utf-8"},
        )
    assert response.status_code == 201, response.text
    assert runtime.calls == [("src", "# 原文\n内容。\n".encode(), "Markdown 来源", metadata)]


@pytest.mark.parametrize("query", [
    "vehicle_model=COROLLA", "vehicle_model=camry", "vehicle_model=CAMRY&model_year=1999",
    "vehicle_model=CAMRY&model_year=2100", "vehicle_model=CAMRY&model_year=20x4",
    "vehicle_model=CAMRY&powertrain=V6", "vehicle_model=CAMRY&powertrain=",
    "model_year=2024", "powertrain=2.5",
])
def test_upload_rejects_unknown_scope_before_runtime(query):
    runtime = FakeRuntime()
    with client_for(runtime) as client:
        response = client.post(
            "/api/v1/knowledge/sources/src/versions?" + query,
            content="正文\n".encode(), headers={"Content-Type": "text/plain; charset=utf-8"},
        )
    assert response.status_code == 422, response.text
    assert runtime.calls == []


def test_upload_metadata_never_derived_from_title_or_content():
    runtime = FakeRuntime()
    with client_for(runtime) as client:
        response = client.post(
            "/api/v1/knowledge/sources/src/versions?title=%E5%87%AF%E7%BE%8E%E7%91%9E2024",
            content="凯美瑞 2024 2.5 双擎\n".encode(), headers={"Content-Type": "text/plain; charset=utf-8"},
        )
    assert response.status_code == 201, response.text
    assert runtime.calls[0][3] == {"vehicle_scopes": []}


@pytest.mark.parametrize("query", [
    "vehicle_model=CAMRY&vehicle_model=RAV4", "vehicle_model=CAMRY&model_year=2024&model_year=2025",
    "vehicle_model=CAMRY&powertrain=2.0&powertrain=2.5", "title=a&title=b",
])
def test_upload_rejects_repeated_parameters(query):
    runtime = FakeRuntime()
    with client_for(runtime) as client:
        response = client.post(
            "/api/v1/knowledge/sources/src/versions?" + query,
            content="正文\n".encode(), headers={"Content-Type": "text/plain; charset=utf-8"},
        )
    assert response.status_code == 422, response.text
    assert runtime.calls == []
