"""P0 回归测试：认证哈希、文档生成、跨轮文档流程、知识库安全加载。"""

import asyncio
import json
import os

import pytest

from app.agents.nodes.document_nodes import (
    _generate_analysis_document,
    _generate_presentation,
    _generate_proposal_document,
)
from app.services.auth import hash_password, verify_password


# ═══════════════════════════════════════════════════════════════
# P0-1 密码哈希：不再依赖 passlib，可真实注册/登录
# ═══════════════════════════════════════════════════════════════

def test_hash_and_verify_roundtrip():
    hashed = hash_password("hello123")
    assert hashed.startswith("$2b$")
    assert verify_password("hello123", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_verify_rejects_malformed_hash_without_raising():
    assert verify_password("hello123", "not-a-bcrypt-hash") is False
    assert verify_password("hello123", "") is False


def test_hash_rejects_over_72_bytes():
    with pytest.raises(ValueError):
        hash_password("密" * 30)  # 90 UTF-8 字节


def test_verify_over_72_bytes_returns_false():
    hashed = hash_password("hello123")
    assert verify_password("a" * 100, hashed) is False


# ═══════════════════════════════════════════════════════════════
# P0-2 文档生成：三种文档不再因未定义变量失败
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "output_dir", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_proposal_document_uses_params(output_dir):
    doc = await _generate_proposal_document(
        {"customer_name": "张三", "project_name": "购车方案"}
    )
    assert os.path.isfile(doc.file_path)
    assert "张三" in doc.file_name
    assert doc.file_name.endswith(".docx")


@pytest.mark.asyncio
async def test_analysis_document_uses_params(output_dir):
    doc = await _generate_analysis_document({"analysis_type": "季度销售分析"})
    assert os.path.isfile(doc.file_path)
    assert "季度销售分析" in doc.file_name
    assert doc.file_name.endswith(".xlsx")


@pytest.mark.asyncio
async def test_presentation_document_uses_params(output_dir):
    doc = await _generate_presentation({"title": "新车上市汇报"})
    assert os.path.isfile(doc.file_path)
    assert "新车上市汇报" in doc.file_name
    with open(doc.file_path, encoding="utf-8") as fh:
        assert "新车上市汇报" in fh.read()


@pytest.mark.asyncio
async def test_document_fallback_keeps_requested_type(output_dir, monkeypatch):
    """生成失败时按原意图降级，而不是偷换成报价单。"""
    from app.agents.nodes import document_nodes

    async def boom(params):
        raise RuntimeError("simulated failure")

    # 让分析文档失败，验证兜底不会再生成报价单
    monkeypatch.setattr(document_nodes, "_generate_analysis_document", boom)
    state = {
        "session_id": "p0-fallback",
        "document_params": {
            "intent": "data_analysis",
            "params": {"analysis_type": "季度分析"},
            "missing": [],
        },
        "generated_documents": [],
        "sales_response": None,
        "suggested_actions": [],
        "context": {},
        "metadata": {},
    }
    result = await document_nodes.generate_document_node(state)
    # 分析报表失败时不伪造内容，也不生成"默认报价单"
    assert result["generated_documents"] == []
    assert "暂时不可用" in result["sales_response"]
    assert "报价单" not in result["sales_response"]


# ═══════════════════════════════════════════════════════════════
# P0-3 文档流程：不会被无关对话无限拉回
# ═══════════════════════════════════════════════════════════════

def _doc_state(**overrides):
    state = {
        "document_params": {
            "intent": "contract_drafting",
            "params": {"customer_name": "张三"},
            "missing": ["车型"],
            "flow_active": True,
            "flow_pending": True,
        },
        "intent_analysis": None,
    }
    state.update(overrides)
    return state


def test_route_continues_flow_when_awaiting_params():
    from app.agents.graphs.sales_graph import _route_after_sales_response

    assert _route_after_sales_response(_doc_state()) == "extract_document_params"


def test_route_stops_flow_when_not_active():
    from app.agents.graphs.sales_graph import _route_after_sales_response

    state = _doc_state()
    state["document_params"]["flow_active"] = False
    assert _route_after_sales_response(state) == "end"


def test_unrelated_question_closes_flow():
    from app.agents.nodes.intent_node import _update_document_flow
    from app.models.chat import UserIntent

    state = _doc_state()
    _update_document_flow(state, UserIntent.PRODUCT_INQUIRY, "凯美瑞和亚洲龙哪个好？")
    assert state["document_params"]["flow_active"] is False


def test_flow_window_expires_after_one_turn():
    from app.agents.nodes.intent_node import _update_document_flow
    from app.models.chat import UserIntent

    state = _doc_state()
    # 第一轮补充参数（非问句）——窗口被消耗但流程仍有效
    _update_document_flow(state, UserIntent.GENERAL_CHAT, "凯美瑞，预算20万")
    assert state["document_params"]["flow_active"] is True
    assert state["document_params"]["flow_pending"] is False
    # 再下一轮闲聊——流程自动失效
    _update_document_flow(state, UserIntent.GENERAL_CHAT, "今天天气不错")
    assert state["document_params"]["flow_active"] is False


def test_explicit_cancel_closes_flow():
    from app.agents.nodes.intent_node import _update_document_flow
    from app.models.chat import UserIntent

    state = _doc_state()
    _update_document_flow(state, UserIntent.GENERAL_CHAT, "算了，不用了")
    assert state["document_params"]["flow_active"] is False


def test_extract_params_does_not_reuse_previous_intent_when_inactive():
    """上一轮流程已失效时，新的文档意图不会被旧合同意图覆盖。"""
    from app.agents.nodes import document_nodes

    state = {
        "session_id": "p0-intent",
        "intent_analysis": type("IA", (), {"intent": document_nodes.UserIntent.QUOTE_GENERATION})(),
        "document_params": {
            "intent": "contract_drafting",
            "params": {},
            "missing": ["车型"],
            "flow_active": False,
        },
        "messages": [],
        "context": {},
        "next_node": None,
    }
    # 不调用 LLM：让 ChatOpenAI 构造直接失败，走 except 兜底分支
    import app.agents.nodes.document_nodes as dn

    class Boom:
        def __init__(self, *a, **kw):
            raise RuntimeError("no llm in tests")

    original = dn.ChatOpenAI
    dn.ChatOpenAI = Boom
    try:
        result = asyncio.run(dn.extract_document_params_node(state))
    finally:
        dn.ChatOpenAI = original
    assert result["document_params"]["intent"] == "quote_generation"


# ═══════════════════════════════════════════════════════════════
# P0-4 知识库：生产环境不依赖 pickle，JSON 快照可安全重建
# ═══════════════════════════════════════════════════════════════

def test_documents_snapshot_roundtrip(tmp_path, monkeypatch):
    from langchain_core.documents import Document

    from app.agents.nodes.knowledge_node import KnowledgeBaseService
    from app.core.config import settings

    monkeypatch.setattr(settings, "vector_store_path", str(tmp_path))
    service = KnowledgeBaseService()
    docs = [Document(page_content="凯美瑞 18.98 万", metadata={"source": "a.md"})]

    service._write_documents_snapshot(docs)
    snapshot_path = tmp_path / "kb_documents.json"
    assert snapshot_path.is_file()

    # 快照必须是纯 JSON（不含 pickle 字节）
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload[0]["content"] == "凯美瑞 18.98 万"

    loaded = service._read_documents_snapshot()
    assert loaded is not None and loaded[0].page_content == "凯美瑞 18.98 万"


def test_corrupt_snapshot_returns_none(tmp_path, monkeypatch):
    from app.agents.nodes.knowledge_node import KnowledgeBaseService
    from app.core.config import settings

    monkeypatch.setattr(settings, "vector_store_path", str(tmp_path))
    (tmp_path / "kb_documents.json").write_text("{not json", encoding="utf-8")
    assert KnowledgeBaseService()._read_documents_snapshot() is None


def test_production_never_enables_dangerous_deserialization(monkeypatch, tmp_path):
    """生产环境加载知识库时不得调用 FAISS.load_local(pickle)。"""
    import app.agents.nodes.knowledge_node as kn
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "vector_store_path", str(tmp_path))
    monkeypatch.setattr(settings, "knowledge_base_path", str(tmp_path / "kb"))
    os.makedirs(tmp_path / "kb", exist_ok=True)
    (tmp_path / "kb" / "a.md").write_text("凯美瑞 18.98 万", encoding="utf-8")

    called = {}

    def fake_load_local(*args, **kwargs):
        called["load_local"] = kwargs
        raise AssertionError("production must not use pickle deserialization")

    class FakeStore:
        pass

    monkeypatch.setattr(kn.FAISS, "load_local", fake_load_local)

    async def fake_create(self, documents, save_snapshot=True):
        return FakeStore()

    monkeypatch.setattr(kn.KnowledgeBaseService, "_create_vector_store_from_documents", fake_create)

    service = kn.KnowledgeBaseService()
    assert asyncio.run(service.initialize()) is True
    assert "load_local" not in called
