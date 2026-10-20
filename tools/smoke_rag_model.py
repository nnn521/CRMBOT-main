"""One bounded gateway compatibility call; never print credentials/content."""
import asyncio
from decimal import Decimal
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.knowledge.budget import BudgetLedger, TokenRates
from app.services.knowledge.model_client import DeepSeekClient


def load_local_config():
    path = ROOT / '.tmp' / 'rag-v2.env'
    return dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines()
                if line.strip() and not line.startswith('#'))


async def main():
    config = load_local_config()
    ledger = BudgetLedger(ROOT / '.tmp' / 'rag-v2-budget.sqlite3', Decimal('50'))
    client = DeepSeekClient(api_key=config['KNOWLEDGE_API_KEY'], model=config['KNOWLEDGE_ANSWER_MODEL'],
                            base_url=config['KNOWLEDGE_API_BASE_URL'], ledger=ledger,
                            rates=TokenRates(Decimal('2'), Decimal('8')), timeout=30)
    started = time.perf_counter()
    result = await client.generate_json(system='返回JSON对象，字段ok固定为true。',
                                         data={'task': 'connection test'}, max_output_tokens=32)
    print({'json_compatible': result == {'ok': True}, 'elapsed_seconds': round(time.perf_counter()-started, 3),
           'budget': ledger.summary()})


if __name__ == '__main__':
    asyncio.run(main())
