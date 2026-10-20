"""Citation transport contract: mocked graph/database/HTTP, no external services."""

from datetime import datetime
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models.chat import CitationInfo, ChatResponse, UserIntent

chat_api = import_module("app.api.v1.chat")


def citation(**overrides):
    return {
        "citation_id": "cite-1",
        "span_id": "span-1",
        "source_id": "source-1",
        "document_version": "v1",
        "title": "车型配置 <script>alert(1)</script>",
        "locator": {"start_line": 3, "end_line": 4, "kind": "paragraph"},
        "quote": "仅适用于指定配置。",
        "url": "/api/v1/knowledge/releases/release-1/citations/span-1",
        **overrides,
    }


def answer_info():
    return {
        "citations": [citation()],
        "knowledge_release_id": "release-1",
        "answer_status": "partial",
        "data_as_of": "2026-10-20",
        "assumptions": ["指定车型和地区"],
        "limitations": ["最终价格以门店为准"],
    }


@pytest.mark.parametrize("url", [
    "C:\\private\\knowledge.txt", "/srv/private/knowledge.txt", "file:///srv/private/knowledge.txt",
    "https://evil.example/api/v1/knowledge/releases/r/citations/s", "//evil.example/source",
    "javascript:alert(1)", "/api/v1/knowledge/../../secret", "/api/v1/knowledge/releases/../citations/s",
    "/api/v1/knowledge/releases/r/citations/%2e%2e", "/api/v1/knowledge/releases/r/citations/%252e%252e",
    "/api/v1/knowledge/releases/r/citations/%2fetc", "/api/v1/knowledge/releases/r/citations/s?next=evil",
])
def test_citation_rejects_non_internal_detail_urls(url):
    with pytest.raises(ValidationError):
        CitationInfo.model_validate(citation(url=url))


def test_citation_schema_and_legacy_response_compatibility():
    value = CitationInfo.model_validate(citation(private_path="/srv/secret", score=0.98))
    assert set(value.model_dump()) == {
        "citation_id", "span_id", "source_id", "document_version", "title", "locator", "quote", "url",
    }
    assert value.title == citation()["title"]  # Preserve text; rendering performs escaping.
    response = ChatResponse(session_id="s", reply="hello", intent=UserIntent.GENERAL_CHAT)
    assert response.citations is None
    assert response.answer_status is None
    for status in ("answered", "partial", "clarification", "unavailable"):
        assert ChatResponse(session_id="s", reply="hello", intent=UserIntent.GENERAL_CHAT, answer_status=status).answer_status == status
    with pytest.raises(ValidationError):
        ChatResponse(session_id="s", reply="hello", intent=UserIntent.GENERAL_CHAT, answer_status="fabricated")


def test_controlled_fields_are_validated_without_metadata_or_context_fallback():
    raw = {
        **answer_info(),
        "citations": [citation(private_path="/srv/private"), citation(url="/srv/secret"), {"quote": "invalid"}],
        "context": {"knowledge_release_id": "forged"},
        "metadata": {"answer_status": "forged"},
        "private_path": "/srv/private",
    }
    clean = chat_api._validated_answer_info(raw)
    assert clean == answer_info()
    assert chat_api._validated_answer_info({"context": answer_info(), "metadata": answer_info()}) == {}
    assert chat_api._validated_answer_info({"answer_status": "forged", "citations": "not a list", "assumptions": {"private": True}}) == {}


def test_history_restores_only_allowlisted_public_fields():
    message = SimpleNamespace(
        id=7, session_id="s", role="assistant", content="reply", intent="general_chat",
        created_at=datetime(2026, 10, 20),
        metadata_json={
            **answer_info(), "private_path": "/srv/secret", "debug": "internal",
            "documents": [{"file_name": "报价.xlsx", "doc_type": "xlsx", "file_path": "/srv/private.xlsx"}],
            "images": ["/api/v1/images/car.png"],
        },
    )
    payload = chat_api._history_message_payload(message)
    assert {name: payload[name] for name in answer_info()} == answer_info()
    assert payload["documents"][0]["file_path"].startswith("/api/v1/documents/")
    assert payload["images"] == ["/api/v1/images/car.png"]
    assert "private_path" not in payload and "debug" not in payload
    message.metadata_json = None
    assert "citations" not in chat_api._history_message_payload(message)
    message.metadata_json = answer_info()
    message.role = "user"
    assert "citations" not in chat_api._history_message_payload(message)


class FakeResult:
    def __init__(self, messages):
        self.messages = messages

    def scalar_one_or_none(self):
        return 1

    def scalars(self):
        return self

    def all(self):
        return self.messages


class FakeDb:
    def __init__(self):
        self.messages = []

    def add(self, message):
        message.id = len(self.messages) + 1
        message.created_at = datetime(2026, 10, 20, 12, 0, len(self.messages))
        self.messages.append(message)

    async def flush(self):
        pass

    async def execute(self, _statement):
        return FakeResult(self.messages)


@pytest.fixture
def client_context(monkeypatch):
    db = FakeDb()
    state = {
        **answer_info(),
        "sales_response": "这是有条件的回答。",
        "intent_analysis": SimpleNamespace(intent=UserIntent.PRODUCT_INQUIRY, high_intent=False),
        "generated_documents": [], "images": [], "knowledge_results": [],
        "context": {"citations": [citation(quote="forged from context")]},
    }
    graph = AsyncMock(return_value=state)
    broadcasts = AsyncMock()
    monkeypatch.setattr(chat_api, "run_sales_agent", graph)
    monkeypatch.setattr(chat_api, "enforce_rate_limit", AsyncMock())
    monkeypatch.setattr(chat_api, "_get_or_create_session_state", AsyncMock(return_value=SimpleNamespace(handover_mode="ai")))
    monkeypatch.setattr(chat_api, "_find_car_images", lambda **_kwargs: [])
    monkeypatch.setattr(chat_api.manager, "broadcast_to_session", broadcasts)
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/api/v1")
    app.dependency_overrides[chat_api.get_current_user] = lambda: {"user_id": 1, "username": "alice", "role": "customer"}
    app.dependency_overrides[chat_api.get_current_session] = lambda: "session_alice"
    app.dependency_overrides[chat_api.get_db_optional] = lambda: db
    app.dependency_overrides[chat_api.get_db] = lambda: db
    with TestClient(app) as client:
        yield client, db, state, graph, broadcasts


def test_http_ws_persistence_and_both_histories_share_citation_contract(client_context):
    client, db, _state, graph, broadcasts = client_context
    response = client.post("/api/v1/chat", json={
        "session_id": "session_alice", "message": "介绍配置", "history": [],
        "context": {**answer_info(), "customer_name": "Alice"},
    })
    assert response.status_code == 200, response.text
    body = response.json()
    expected = answer_info()
    assert {name: body[name] for name in expected} == expected
    assert graph.await_args.kwargs["context"] == {"customer_name": "Alice"}
    assert graph.await_args.kwargs["history"] is None
    persisted = db.messages[-1].metadata_json
    assert {name: persisted[name] for name in expected} == expected
    assert "context" not in persisted and "metadata" not in persisted
    assistant_events = [call.args[1]["message"] for call in broadcasts.await_args_list
                        if call.args[1].get("type") == "new_message" and call.args[1]["message"]["role"] == "assistant"]
    assert len(assistant_events) == 2
    assert assistant_events[0]["id"] == body["message_id"]
    for message in assistant_events:
        assert {name: message[name] for name in expected} == expected
    for path in ("/api/v1/chat/history/session_alice", "/api/v1/chat/sessions/session_alice/messages"):
        history = client.get(path)
        assert history.status_code == 200, history.text
        message = history.json()["messages"][-1]
        assert message["id"] == body["message_id"]
        assert {name: message[name] for name in expected} == expected


def test_invalid_state_fields_never_reach_http_ws_or_storage(client_context):
    client, db, state, _graph, broadcasts = client_context
    state.update({
        "citations": [citation(url="/srv/private/source.txt"), citation(private_path="/srv/secret")],
        "answer_status": "made_up", "data_as_of": {"debug": "internal"},
        "assumptions": "unvalidated string", "private_path": "/srv/secret",
    })
    response = client.post("/api/v1/chat", json={"session_id": "session_alice", "message": "介绍配置"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["citations"] == [citation()]
    assert body["answer_status"] is None
    assert body["data_as_of"] is None
    assert body["assumptions"] is None
    assert "private_path" not in db.messages[-1].metadata_json
    assert "answer_status" not in db.messages[-1].metadata_json
    for call in broadcasts.await_args_list:
        event = call.args[1]
        if event.get("type") == "new_message" and event["message"]["role"] == "assistant":
            assert event["message"]["citations"] == [citation()]
            assert "answer_status" not in event["message"]


def test_context_cannot_supply_missing_state_citations(client_context):
    client, db, state, _graph, _broadcasts = client_context
    for name in answer_info():
        state.pop(name)
    response = client.post("/api/v1/chat", json={
        "session_id": "session_alice", "message": "介绍配置", "context": answer_info(),
    })
    assert response.status_code == 200, response.text
    assert response.json()["citations"] is None
    assert response.json()["knowledge_release_id"] is None
    assert "citations" not in db.messages[-1].metadata_json
