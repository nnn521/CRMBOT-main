"""Explicit persistent-job worker; no migrations or automatic publication.

Run from backend/: python scripts/knowledge_worker.py [--once]
Requires RAG_V2_ENABLED=true and KNOWLEDGE_DATABASE_URL explicitly configured.
Uses only the separate knowledge DSN; never falls back to DATABASE_URL.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.knowledge.runtime import open_knowledge_runtime


async def run(*, once: bool, poll_seconds: float) -> int:
    worker = "knowledge-" + uuid4().hex
    while True:
        try:
            async with open_knowledge_runtime() as runtime:
                claimed = await runtime.run_one_job(worker)
        except Exception:
            # No exception/DSN/key dumps. Configure prerequisites and retry using
            # the durable database queue; the API never reports pretend success.
            print("Knowledge worker unavailable; check separate database, migrations and model configuration.", file=sys.stderr)
            return 1
        if once:
            return 0
        if not claimed:
            await asyncio.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="claim at most one job")
    parser.add_argument("--poll-seconds", type=float, default=2)
    args = parser.parse_args()
    if not 0.1 <= args.poll_seconds <= 60:
        parser.error("poll-seconds must be between 0.1 and 60")
    try:
        if sys.platform == "win32":
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                return runner.run(run(once=args.once, poll_seconds=args.poll_seconds))
        return asyncio.run(run(once=args.once, poll_seconds=args.poll_seconds))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
