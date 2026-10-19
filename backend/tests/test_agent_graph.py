"""Agent 图端到端回归测试（内存模式 + Fake LLM，无外部依赖）。"""

import re

import pytest

from app.agents.graphs import run_sales_agent, clear_session_checkpoint
from app.agents.graphs.sales_graph import _shared_memory_saver

# ── Fake LLM ──────────────────────────────────────────────────

FAKE = {"intent": "general_chat", "reply_template": "测试回复:{last}"}


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


def _extract_user_message(system_prompt: str, fallback: str) -> str:
    """从带防护标签的 prompt 中提取用户原始消息。"""
    m = re.search(r"<user_message>\s*(.*?)\s*</user_message>", system_prompt, re.DOTALL)
    if m:
        return m.group(1).strip()
    return fallback


class FakeChatOpenAI:
    def __init__(self, **kwargs):
        pass

    async def ainvoke(self, messages):
        system = messages[0].content if messages else ""
        last = messages[-1].content if messages else ""
        if "意图识别" in system:
            return _FakeResponse(
                '{"intent": "%s", "confidence": 0.9, "entities": {}, '
                '"reasoning": "test", "high_intent": false}' % FAKE["intent"]
            )
        if "参数提取" in system:
            return _FakeResponse(
                '{"params": {"customer_name": "测试客户", "products": ['
                '{"name": "凯美瑞", "quantity": 1, "unit_price": 189800}]}, '
                '"missing_params": []}'
            )
        user_message = _extract_user_message(system, last)
        return _FakeResponse(FAKE["reply_template"].format(last=user_message))


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    FAKE["intent"] = "general_chat"
    FAKE["reply_template"] = "测试回复:{last}"
    # knowledge_node 在函数内部延迟导入 ChatOpenAI，因此 patch 源模块。
    # 这样无论节点何时导入，都会拿到 Fake 实现。
    monkeypatch.setattr("langchain_openai.ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr("app.agents.nodes.intent_node.ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr("app.agents.nodes.response_node.ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr("app.agents.nodes.document_nodes.ChatOpenAI", FakeChatOpenAI)
    # 知识库节点会访问 Ollama；测试中直接跳过向量检索，走无知识回退路径。
    monkeypatch.setattr(
        "app.agents.nodes.knowledge_node.kb_service.search",
        _fake_search,
        raising=True,
    )
    yield


async def _fake_search(*args, **kwargs):
    return []


def _message_texts(state: dict) -> list[str]:
    return [str(m.content) for m in state.get("messages", [])]


@pytest.mark.asyncio
async def test_general_chat_returns_llm_reply():
    state = await run_sales_agent(session_id="graph-t1", message="你好")
    assert state["sales_response"] == "测试回复:你好"
    assert len(_message_texts(state)) == 2  # 用户消息 + AI 回复


@pytest.mark.asyncio
async def test_multiturn_messages_grow_linearly_without_duplication():
    thread = "graph-multi"
    for i in range(3):
        state = await run_sales_agent(session_id=thread, message=f"第{i}轮")
    texts = _message_texts(state)
    # 3 轮 = 3 用户 + 3 AI，绝不因历史回传/节点整包回传而重复膨胀
    assert len(texts) == 6, texts
    assert state["sales_response"] == "测试回复:第2轮"
    assert texts[-1] == "测试回复:第2轮"


@pytest.mark.asyncio
async def test_vision_flow_sets_sales_response(monkeypatch):
    FAKE["intent"] = "general_chat"  # 带图片时会被强制回退为 analyze_car_image

    async def fake_vision(image_url: str) -> str:
        return "识别到保时捷911 火山灰金属漆"

    monkeypatch.setattr(
        "app.agents.nodes.multimodal_node._call_glm4v_vision_api", fake_vision
    )
    state = await run_sales_agent(
        session_id="graph-vision",
        message="看看这台车",
        input_image_url="https://example.com/car.jpg",
    )
    assert "识别到保时捷911" in state["sales_response"]
    assert state["intent_analysis"] is not None
    assert state["intent_analysis"].intent.value == "analyze_car_image"


@pytest.mark.asyncio
async def test_quote_generation_writes_document(monkeypatch, tmp_path):
    FAKE["intent"] = "quote_generation"
    from app.core.config import settings

    monkeypatch.setattr(settings, "output_dir", str(tmp_path))

    state = await run_sales_agent(session_id="graph-quote", message="帮我生成报价单")
    docs = state["generated_documents"]
    assert len(docs) == 1
    assert "报价单" in state["sales_response"]
    file_name = getattr(docs[0], "file_name", None) or docs[0].get("file_name")
    assert (tmp_path / file_name).exists()


@pytest.mark.asyncio
async def test_clear_session_checkpoint_forgets_memory():
    if not hasattr(_shared_memory_saver, "delete_thread"):
        pytest.skip("当前 langgraph 版本不支持 delete_thread")
    thread = "graph-forget"
    await run_sales_agent(session_id=thread, message="第一轮")
    await run_sales_agent(session_id=thread, message="第二轮")

    cleared = await clear_session_checkpoint(thread)
    assert cleared is True

    state = await run_sales_agent(session_id=thread, message="全新开始")
    assert len(_message_texts(state)) == 2
    assert state["sales_response"] == "测试回复:全新开始"
