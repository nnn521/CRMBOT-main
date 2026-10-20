"""One disposable end-to-end smoke: upload -> build -> publish -> answer.

Uses a fresh loopback-only pgvector container, the locally installed embedding
model and the configured answer gateway. Content is synthetic TEST DATA, never
an official source. Credentials from private files are never printed.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx
import psycopg
from psycopg import AsyncConnection

from app.core.config import Settings
from app.services.knowledge.budget import BudgetLedger
from app.services.knowledge.runtime import open_knowledge_runtime

DOC = """# 凯美瑞 2027款 双擎 车辆说明


## 质保条件

- 整车质保期为 3 年或 10 万公里，以先到者为准。
- 上述质保仅适用于家用车辆，营运车辆除外。

## 保养建议

- 建议每 10000 公里或 12 个月进行一次保养。
"""


def load_env(path: Path) -> dict:
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#"))


def start_container() -> tuple[str, str]:
    name = "crmbot-rag-smoke-" + uuid.uuid4().hex[:12]
    password = secrets.token_hex(24)
    with tempfile.TemporaryDirectory(prefix="crmbot-rag-smoke-") as directory:
        env_path = Path(directory) / "postgres.env"
        env_path.write_text(f"POSTGRES_PASSWORD={password}\nPOSTGRES_DB=smoke\n", encoding="utf-8")
        os.chmod(env_path, 0o600)
        result = subprocess.run(["docker", "run", "--name", name, "--env-file", str(env_path),
                                 "-p", "127.0.0.1::5432", "-d", "pgvector/pgvector:0.8.0-pg16"],
                                capture_output=True, text=True, timeout=240)
        if result.returncode:
            raise RuntimeError("could not start smoke database: " + result.stderr[-500:])
    for _ in range(60):
        ready = subprocess.run(["docker", "exec", name, "pg_isready", "-U", "postgres"],
                               capture_output=True, timeout=5)
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("smoke database did not become ready")
    port = subprocess.run(["docker", "port", name, "5432/tcp"], capture_output=True,
                          text=True, check=True, timeout=10).stdout.strip().rsplit(":", 1)[-1]
    return name, f"postgresql://postgres:{password}@127.0.0.1:{port}/smoke"


async def main() -> int:
    env = load_env(ROOT / ".tmp" / "rag-v2.env")
    tags = httpx.get("http://127.0.0.1:11434/api/tags", timeout=10).json()["models"]
    model = next(item for item in tags if item["name"].startswith(env["KNOWLEDGE_EMBEDDING_MODEL"]))
    revision = model["digest"]
    name, dsn = start_container()
    started = time.perf_counter()
    try:
        sys.path.insert(0, str(ROOT / "backend" / "scripts"))
        from migrate_knowledge import migrate as run_migration
        async with await AsyncConnection.connect(dsn, autocommit=True, connect_timeout=10) as connection:
            applied = await run_migration(connection)
        print("migrations:", len(applied), flush=True)

        config = Settings(_env_file=None, rag_v2_enabled=True, knowledge_database_url=dsn,
            knowledge_embedding_model=env["KNOWLEDGE_EMBEDDING_MODEL"],
            knowledge_embedding_revision="sha256:" + revision, knowledge_embedding_dimension=1024,
            knowledge_ollama_base_url=env["KNOWLEDGE_OLLAMA_BASE_URL"],
            knowledge_http_timeout_seconds=30,
            knowledge_api_key=env["KNOWLEDGE_API_KEY"], knowledge_api_base_url=env["KNOWLEDGE_API_BASE_URL"],
            knowledge_answer_model=env["KNOWLEDGE_ANSWER_MODEL"],
            knowledge_budget_cny=float(env["KNOWLEDGE_BUDGET_CNY"]),
            knowledge_input_per_million_cny=float(env["KNOWLEDGE_INPUT_PER_MILLION_CNY"]),
            knowledge_output_per_million_cny=float(env["KNOWLEDGE_OUTPUT_PER_MILLION_CNY"]),
            knowledge_budget_path=env["KNOWLEDGE_BUDGET_PATH"],
            knowledge_answer_mode="synthesized", knowledge_upload_max_bytes=262144)
        os.environ["KNOWLEDGE_DATABASE_URL"] = dsn
        async with open_knowledge_runtime(config) as runtime:
            source = await runtime.create_source(doc_id="smoke-test-only", source_uri="urn:smoke:test-only")
            upload = await runtime.upload(source["source_id"], DOC.encode("utf-8"), title="测试资料（非官方）",
                metadata={"vehicle_scopes": [{"model": "CAMRY", "year": 2027, "powertrain": "2.0 双擎"}]})
            job = await runtime.enqueue_build([upload["version_id"]], idempotency_key="smoke-" + uuid.uuid4().hex,
                                              requested_by="smoke")
            print("build queued:", job["status"], flush=True)
            await runtime.run_one_job("smoke-worker")
            status = await runtime.build_status(uuid.UUID(job["job_id"]))
            print("build:", status["status"], status["release_status"],
                  (await runtime.storage._one("SELECT last_error FROM knowledge.ingestion_job WHERE job_id=%s",
                                              (job["job_id"],))), flush=True)
            if status["status"] != "succeeded":
                return 1
            published = await runtime.publish(status["release_id"])
            print("published:", published["status"], flush=True)
            answer = await runtime.answer_bundle("2027款凯美瑞双擎的质保条件是什么？")
            print("answer_status:", answer["answer_status"], flush=True)
            print("limitations:", answer["limitations"], flush=True)
            print("citations:", len(answer["citations"]), flush=True)
            print("reply:", answer["reply"][:300].replace("\n", " "), flush=True)
        ledger = BudgetLedger(Path(env["KNOWLEDGE_BUDGET_PATH"]), Decimal(env["KNOWLEDGE_BUDGET_CNY"]))
        print("budget:", ledger.summary(), flush=True)
        print("elapsed_seconds:", round(time.perf_counter() - started, 2), flush=True)
        return 0
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=60)
        print("smoke container removed", flush=True)


if __name__ == "__main__":
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            raise SystemExit(runner.run(main()))
    raise SystemExit(asyncio.run(main()))
