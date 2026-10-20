"""Start only the isolated RAG v2 database and model infrastructure."""
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
private = ROOT / '.tmp'
private.mkdir(exist_ok=True)
config = private / 'rag-infrastructure.env'
if not config.exists():
    config.write_text('RAG_V2_POSTGRES_PASSWORD=' + secrets.token_hex(32) + '\n', encoding='utf-8')
    config.chmod(0o600)
subprocess.run(['docker', 'compose', '--env-file', str(config), '-f',
                str(ROOT / 'backend' / 'docker-compose.rag-v2.yml'), '--profile', 'ollama',
                'up', '-d'], check=True, timeout=180)
print('Isolated RAG infrastructure started. Credentials remain in Git-ignored local configuration.')
