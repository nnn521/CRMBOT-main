from contextlib import asynccontextmanager

import pytest

from app.agents.state import create_initial_state
from app.agents.graphs.sales_graph import _sanitize_final_state
from app.agents.nodes.knowledge_node import knowledge_retrieval_node
from app.agents.nodes.response_node import sales_response_node
from app.core.config import settings


def test_new_turn_resets_source_metadata_instead_of_reusing_checkpoint():
    state = create_initial_state('test', '你好')
    assert state['citations'] == []
    assert state['knowledge_release_id'] is None
    assert state['answer_status'] is None
    assert state['limitations'] == []


def test_final_state_keeps_citation_contract():
    result = _sanitize_final_state({'citations': [{'span_id': 'a'}],
                                   'knowledge_release_id': 'r', 'answer_status': 'partial',
                                   'assumptions': ['condition'], 'limitations': ['missing']}, 'session')
    assert result['knowledge_release_id'] == 'r'
    assert result['citations'] == [{'span_id': 'a'}]
    assert result['limitations'] == ['missing']


@pytest.mark.asyncio
async def test_v2_answer_is_added_once_and_downstream_does_not_regenerate(monkeypatch):
    from app.services.knowledge import runtime
    class FakeRuntime:
        async def answer_bundle(self, query, *, previous_user_messages=()):
            assert query == '2027款凯美瑞具体配置'
            return {'reply': '已提供来源原文', 'citations': [], 'knowledge_release_id': 'release',
                    'answer_status': 'answered', 'limitations': ['原文引述模式']}
    @asynccontextmanager
    async def opened():
        yield FakeRuntime()
    monkeypatch.setattr(runtime, 'open_knowledge_runtime', opened)
    monkeypatch.setattr(settings, 'rag_v2_enabled', True)
    state = create_initial_state('test', '2027款凯美瑞具体配置')
    updated = await knowledge_retrieval_node(state)
    assert len(updated['messages']) == 1
    assert updated['knowledge_release_id'] == 'release'
    downstream = await sales_response_node(dict(updated))
    assert 'messages' not in downstream
    assert downstream['sales_response'] == '已提供来源原文'


@pytest.mark.asyncio
async def test_v2_outage_does_not_fall_back_to_unverified_prices(monkeypatch):
    from app.services.knowledge import runtime
    @asynccontextmanager
    async def opened():
        raise RuntimeError('do not expose credentials or DSN')
        yield
    monkeypatch.setattr(runtime, 'open_knowledge_runtime', opened)
    monkeypatch.setattr(settings, 'rag_v2_enabled', True)
    state = create_initial_state('test', '2027款凯美瑞官方指导价')
    updated = await knowledge_retrieval_node(state)
    assert updated['answer_status'] == 'unavailable'
    assert 'credentials' not in updated['sales_response']
    assert updated['citations'] == []


@pytest.mark.asyncio
async def test_v2_intent_routes_knowledge_without_paid_classifier(monkeypatch):
    from app.agents.nodes import intent_node
    def forbidden(**kwargs):
        pytest.fail('knowledge classification must not create an unbudgeted model client')
    monkeypatch.setattr(settings, 'rag_v2_enabled', True)
    monkeypatch.setattr(intent_node, 'ChatOpenAI', forbidden)
    updated = await intent_node.intent_recognition_node(create_initial_state('test', '2027款凯美瑞油耗'))
    assert updated['next_node'] == 'knowledge_retrieval'
    assert 'messages' not in updated


@pytest.mark.asyncio
async def test_v2_loan_uses_explicit_tool_without_knowledge_database(monkeypatch):
    from app.services.knowledge import runtime
    @asynccontextmanager
    async def forbidden():
        pytest.fail('loan must not require database or model')
        yield
    monkeypatch.setattr(runtime, 'open_knowledge_runtime', forbidden)
    monkeypatch.setattr(settings, 'rag_v2_enabled', True)
    updated = await knowledge_retrieval_node(create_initial_state('test', '本金120000元，年利率0%，期限12个月'))
    assert updated['answer_status'] == 'answered'
    assert '10,000.00' in updated['sales_response']
    assert updated['citations'] == []
    assert len(updated['messages']) == 1
