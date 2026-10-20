"""Opt-in real PostgreSQL/pgvector wiki-job integration; fake model ONLY.

TEST_KNOWLEDGE_DATABASE_URL must point to an empty disposable database without a
knowledge schema. This test migrates/cleans only its own schema, following the
storage/API integration convention. No repository, connection, SQL, lease,
compiler, persistence or review is mocked. Run serially with other schema owners.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

from app.services.knowledge.domain import Evidence, SourceLocator, document_fingerprint
from app.services.knowledge.storage import KnowledgeStorage, ReleaseManifest, corpus_checksum
from app.services.knowledge.wiki_jobs import WikiJobService


@pytest.mark.skipif(not os.environ.get("TEST_KNOWLEDGE_DATABASE_URL"),
                    reason="empty disposable PostgreSQL/pgvector not explicitly configured")
def test_real_wiki_jobs_compile_review_revocation_and_fencing():
    import psycopg

    async def exercise():
        dsn = os.environ["TEST_KNOWLEDGE_DATABASE_URL"]
        async with await psycopg.AsyncConnection.connect(dsn, autocommit=True, connect_timeout=10) as connection:
            exists = await connection.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'knowledge'")
            if await exists.fetchone():
                pytest.fail("requires empty disposable database; refusing existing knowledge schema")
            owned = False
            try:
                path = Path(__file__).resolve().parents[1] / "scripts" / "migrate_knowledge.py"
                spec = importlib.util.spec_from_file_location("knowledge_wiki_jobs_migration", path)
                assert spec is not None and spec.loader is not None
                runner = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = runner
                spec.loader.exec_module(runner)
                await runner.migrate(connection)
                owned = True
                store = KnowledgeStorage(connection)
                text = "仅限本店：价格123456元需置换；库存为2026年10月20日记录，须实时查询。"
                original = Evidence("wiki-document", document_fingerprint(text), text, ("车型",),
                                    SourceLocator("wiki-source.md", 1, 1))
                await store.create_source("wiki-source", original.doc_id, "urn:test:wiki-source")
                await store.add_version(original.doc_version, "wiki-source", text.encode("utf-8"), "车型来源")
                await store.add_span(original.span_id, original.doc_version, original.content,
                                     asdict(original.locator), original.section_path)
                chunk = {"chunk_id": "wiki-chunk", "span_id": original.span_id,
                         "version_id": original.doc_version, "content": text, "token_count": 30}
                artifact = b"wiki-jobs-test-bm25"
                manifest = ReleaseManifest(
                    embedding_model="fake-embedding", embedding_revision="test-v1",
                    embedding_dim=3, embedding_normalized=True, expected_chunks=1,
                    corpus_sha256=corpus_checksum([chunk]), bm25_sha256=document_fingerprint(artifact),
                )

                async def prepare_target(release_id):
                    await store.create_release(release_id, manifest)
                    await store.add_chunk(release_id, **chunk, embedding=[1, 0, 0])

                await prepare_target("wiki-source-release")
                await store.mark_ready("wiki-source-release", artifact)
                await store.activate_release("wiki-source-release")
                await prepare_target("wiki-target-release")

                class ExactQuoteModel:
                    def __init__(self, action=None):
                        self.action, self.calls = action, 0

                    async def generate_json(self, *, system, data, max_output_tokens):
                        self.calls += 1
                        assert "输入安全规则" in system
                        assert data["evidence"] == [{"span_id": original.span_id, "content": text}]
                        if self.action:
                            await self.action()
                        return {"title": "车型来源摘录", "sections": [{"heading": "完整原文", "claims": [
                            {"quote": text, "span_id": original.span_id}]}]}

                async def enqueue_and_claim(service, key, target, *, attempts=1):
                    queued = await service.enqueue(
                        key, source_release_id="wiki-source-release", target_release_id=target,
                        topic="车型条件", span_ids=[original.span_id], max_attempts=attempts,
                    )
                    claimed = await store.claim_job("wiki-test-worker", lease_seconds=60)
                    assert claimed is not None and claimed["job_id"] == queued["job_id"]
                    return claimed

                model = ExactQuoteModel()
                service = WikiJobService(store, model, compiler_model="offline-exact-quote")
                first = await enqueue_and_claim(service, "wiki-success", "wiki-target-release")
                outcome = await service.process_claimed(first)
                assert outcome.status == "succeeded" and model.calls == 1
                cursor = await connection.execute(
                    "SELECT status, title, body FROM knowledge.wiki_draft WHERE release_id=%s AND draft_id=%s",
                    ("wiki-target-release", outcome.draft_id),
                )
                draft_status, title, body = await cursor.fetchone()
                assert draft_status == "draft" and title == "车型来源摘录"
                assert json.loads(body)["review_required"] is True
                assert "实时业务工具" in body
                cursor = await connection.execute("""SELECT c.claim_text,c.conditions,dep.span_id,dep.version_id
                    FROM knowledge.wiki_claim c JOIN knowledge.claim_dependency dep
                      ON dep.release_id=c.release_id AND dep.claim_id=c.claim_id
                    WHERE c.release_id=%s AND c.draft_id=%s""", ("wiki-target-release", outcome.draft_id))
                persisted = await cursor.fetchall()
                assert len(persisted) == 1
                claim_text, conditions, span_id, version_id = persisted[0]
                assert (claim_text, span_id, version_id) == (text, original.span_id, original.doc_version)
                assert conditions["timeless"] is False and conditions["requires_fresh_source"] is True
                cursor = await connection.execute("SELECT status,lease_token,last_error FROM knowledge.ingestion_job WHERE job_id=%s",
                                                  (first["job_id"],))
                assert await cursor.fetchone() == ("succeeded", None, None)
                assert (await store.pin_active_release())["release_id"] == "wiki-source-release"
                # No automatic approval: schema blocks readiness until explicit review.
                with pytest.raises(psycopg.Error):
                    await store.mark_ready("wiki-target-release", artifact)
                await service.review("wiki-target-release", outcome.draft_id, approved=True)
                cursor = await connection.execute("SELECT status FROM knowledge.wiki_draft WHERE release_id=%s AND draft_id=%s",
                                                  ("wiki-target-release", outcome.draft_id))
                assert await cursor.fetchone() == ("approved",)
                assert (await store.pin_active_release())["release_id"] == "wiki-source-release"

                # Real expired/reclaimed token: stale service cannot write/finish.
                await prepare_target("wiki-fencing-target")
                stale = await enqueue_and_claim(service, "wiki-fencing", "wiki-fencing-target", attempts=2)
                await connection.execute("UPDATE knowledge.ingestion_job SET lease_until=clock_timestamp()-interval '1 second' WHERE job_id=%s",
                                         (stale["job_id"],))
                fresh = await store.claim_job("wiki-next-worker", lease_seconds=60)
                assert fresh is not None and fresh["lease_token"] != stale["lease_token"]
                previous_calls = model.calls
                lost = await service.process_claimed(stale)
                assert lost.status == "lease_lost" and model.calls == previous_calls
                cursor = await connection.execute("SELECT count(*) FROM knowledge.wiki_draft WHERE release_id=%s", ("wiki-fencing-target",))
                assert await cursor.fetchone() == (0,)
                assert (await service.process_claimed(fresh)).status == "succeeded"

                # Source is revoked in the fake MODEL boundary using REAL SQL;
                # compiler's post-call storage recheck must prevent all writes.
                await prepare_target("wiki-revoked-target")
                async def revoke_during_model():
                    await store.revoke_source("wiki-source", reason="withdrawn in integration", revoked_by="test-human")
                revoked_model = ExactQuoteModel(revoke_during_model)
                revoked_service = WikiJobService(store, revoked_model, compiler_model="offline-exact-quote")
                revoked_job = await enqueue_and_claim(revoked_service, "wiki-revoked", "wiki-revoked-target")
                revoked = await revoked_service.process_claimed(revoked_job)
                assert revoked.status == "failed" and revoked.error_code == "wiki_source_unavailable"
                assert revoked_model.calls == 1
                for table in ("wiki_draft", "wiki_claim", "claim_dependency"):
                    cursor = await connection.execute(
                        f"SELECT count(*) FROM knowledge.{table} WHERE release_id=%s", ("wiki-revoked-target",))
                    assert await cursor.fetchone() == (0,)
                cursor = await connection.execute("SELECT status,last_error FROM knowledge.ingestion_job WHERE job_id=%s",
                                                  (revoked_job["job_id"],))
                assert await cursor.fetchone() == ("failed", "wiki_source_unavailable")
                assert await store.get_citation("wiki-source-release", original.span_id) is None
            finally:
                if owned:
                    await connection.execute("DROP SCHEMA knowledge CASCADE")

    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(exercise())
    else:
        asyncio.run(exercise())
