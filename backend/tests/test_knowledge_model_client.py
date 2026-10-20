import asyncio
from decimal import Decimal

import httpx
import pytest

from app.services.knowledge.budget import BudgetExceeded, BudgetLedger, TokenRates
from app.services.knowledge.model_client import DeepSeekClient, OllamaEmbeddingClient


def test_budget_prevents_network_call(tmp_path):
    def handle(request):
        pytest.fail('exhausted budget must not make a request')
    client = DeepSeekClient(api_key='test-only', model='test', rates=TokenRates(Decimal('2'), Decimal('8')),
                            ledger=BudgetLedger(tmp_path / 'usage.db', Decimal('0.000001')),
                            transport=httpx.MockTransport(handle))
    with pytest.raises(BudgetExceeded):
        asyncio.run(client.generate_json(system='test', data={'query': 'test'}))


def test_paid_invalid_json_is_accounted_without_retry(tmp_path):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
                                        'choices': [{'message': {'content': 'invalid'}}]})
    ledger = BudgetLedger(tmp_path / 'usage.db', Decimal('1'))
    client = DeepSeekClient(api_key='test-only', model='test', rates=TokenRates(Decimal('2'), Decimal('8')),
                            ledger=ledger, transport=httpx.MockTransport(handle))
    with pytest.raises(ValueError):
        asyncio.run(client.generate_json(system='test', data={'query': 'test'}))
    assert len(calls) == 1
    assert ledger.summary()['accounted_cny'] == '0.00006'


def test_ambiguous_provider_failure_retains_budget(tmp_path):
    ledger = BudgetLedger(tmp_path / 'usage.db', Decimal('1'))
    client = DeepSeekClient(api_key='test-only', model='test', rates=TokenRates(Decimal('2'), Decimal('8')),
                            ledger=ledger, transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(RuntimeError):
        asyncio.run(client.generate_json(system='test', data={'query': 'test'}))
    assert Decimal(ledger.summary()['pending_reserved_cny']) > 0


@pytest.mark.parametrize('vectors', [[[1, 2, 3]], [[0, 0]], [[True, 1]], []])
def test_embedding_rejects_dimension_zero_and_invalid_values(vectors):
    client = OllamaEmbeddingClient(base_url='http://localhost:11434', model='test', dimension=2,
                                   transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'embeddings': vectors})))
    with pytest.raises(ValueError):
        asyncio.run(client.embed(['query']))


def test_embedding_normalizes_values():
    client = OllamaEmbeddingClient(base_url='http://localhost:11434', model='test', dimension=2,
                                   transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'embeddings': [[3, 4]]})))
    assert asyncio.run(client.embed(['query']))[0] == pytest.approx([0.6, 0.8])
