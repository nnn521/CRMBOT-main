"""Join existing private RAG settings without printing credentials.

Keeps the feature disabled until explicit acceptance. Never changes app .env.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines()
                if line.strip() and not line.startswith('#'))


def main():
    path = ROOT / '.tmp' / 'rag-v2.env'
    config = load(path)
    config['KNOWLEDGE_BUDGET_PATH'] = (ROOT / '.tmp' / 'rag-v2-budget.sqlite3').as_posix()
    config['KNOWLEDGE_OLLAMA_BASE_URL'] = 'http://127.0.0.1:11434'
    config['KNOWLEDGE_EMBEDDING_MODEL'] = 'bge-m3'
    config['KNOWLEDGE_EMBEDDING_DIMENSION'] = '1024'
    config['RAG_V2_ENABLED'] = 'false'
    path.write_text(''.join(f'{key}={value}\n' for key, value in config.items()), encoding='utf-8')
    path.chmod(0o600)
    print('Private settings now use the existing absolute budget ledger. No database credentials were copied; RAG v2 stays disabled.')


if __name__ == '__main__':
    main()
