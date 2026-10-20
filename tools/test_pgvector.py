"""Run real storage lifecycle tests in a fresh loopback-only password-protected DB.

Creates a dedicated Docker container without a persistent volume. Removes only
that container on completion; never connects to the application's database.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import uuid


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    name = 'crmbot-rag-test-' + uuid.uuid4().hex[:12]
    password = secrets.token_hex(24)
    with tempfile.TemporaryDirectory(prefix='crmbot-rag-credentials-') as directory:
        env_path = Path(directory) / 'postgres.env'
        env_path.write_text(f'POSTGRES_PASSWORD={password}\nPOSTGRES_DB=crmbot_ragv2_test\n', encoding='utf-8')
        os.chmod(env_path, 0o600)
        result = subprocess.run(['docker', 'run', '--name', name, '--env-file', str(env_path),
                                 '-p', '127.0.0.1::5432', '-d', 'pgvector/pgvector:0.8.0-pg16'],
                                capture_output=True, text=True, timeout=240)
        if result.returncode:
            print('Could not create isolated test database:', result.stderr[-2000:])
            return result.returncode
        try:
            for _ in range(45):
                ready = subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'postgres'],
                                       capture_output=True, timeout=5)
                if ready.returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError('isolated database did not become ready')
            port_result = subprocess.run(['docker', 'port', name, '5432/tcp'], capture_output=True,
                                         text=True, check=True, timeout=10)
            port = int(port_result.stdout.strip().rsplit(':', 1)[-1])
            env = os.environ.copy()
            env['TEST_KNOWLEDGE_DATABASE_URL'] = f'postgresql://postgres:{password}@127.0.0.1:{port}/crmbot_ragv2_test'
            env['DATABASE_URL'] = ''
            env['PYTHONPATH'] = str(root / 'backend' / 'pylib')
            print('Running isolated PostgreSQL/pgvector lifecycle tests; credentials are not logged.', flush=True)
            return subprocess.run([sys.executable, '-m', 'pytest', 'tests/test_knowledge_storage.py',
                                   'tests/test_knowledge_api.py', 'tests/test_knowledge_wiki_jobs_postgres.py',
                                   '-q', '--tb=short'], cwd=root / 'backend', env=env, timeout=180).returncode
        finally:
            cleanup = subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=30)
            print('Isolated test container removed.' if cleanup.returncode == 0 else
                  f'Cleanup failed; remove dedicated container {name} manually.', flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
