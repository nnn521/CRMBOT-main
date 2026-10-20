"""Offline wiki job lifecycle/transaction regressions; no model/database calls."""

from copy import deepcopy
from dataclasses import asdict
from uuid import uuid4

import pytest

from app.services.knowledge.domain import Evidence, SourceLocator, document_fingerprint
from app.services.knowledge.storage import LeaseLost
from app.services.knowledge.wiki_jobs import KIND, WikiJobRequest, WikiJobService


def evidence():
    text = "仅限本店：价格123456元需置换；库存为2026年10月20日记录，须实时查询。"
    return Evidence("doc-1", document_fingerprint(text), text, ("车型",), SourceLocator("doc.md", 1, 1))


class FakeClient:
    def __init__(self, item, *, fail=False, callback=None, partial=False):
        self.item, self.fail, self.callback, self.partial = item, fail, callback, partial
        self.calls = 0

    async def generate_json(self, **kwargs):
        self.calls += 1
        if self.callback:
            self.callback()
        if self.fail:
            raise RuntimeError("sk-SECRET-DO-NOT-LEAK provider exception")
        return {"title": "车型原文摘录", "sections": [{"heading": "来源", "claims": [
            {"quote": "价格123456元" if self.partial else self.item.content,
             "span_id": self.item.span_id}]}]}


class FakeTransaction:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        self.backup = deepcopy((self.store.drafts, self.store.claims, self.store.dependencies, self.store.finished))

    async def __aexit__(self, kind, value, traceback):
        if kind:
            self.store.drafts, self.store.claims, self.store.dependencies, self.store.finished = self.backup


class FakeCursor:
    def __init__(self, store):
        self.store = store
        self.row = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def execute(self, sql, params):
        self.store.sql.append(sql)
        if "SELECT doc_id" in sql:
            self.row = {"doc_id": self.store.item.doc_id}
        elif "SELECT c.span_id FROM knowledge.retrieval_chunk" in sql:
            self.row = None if self.store.target_published or self.store.dependency_missing else {"span_id": params[1]}
        elif "SELECT job_id FROM knowledge.ingestion_job" in sql:
            self.row = {"job_id": params[0]} if self.store.valid_lease else None
        elif "SELECT c.release_id" in sql:
            self.row = self.store.row if not self.store.revoked else None
        elif "INSERT INTO knowledge.wiki_draft" in sql:
            if self.store.target_published:
                raise ValueError("release must be building")
            self.store.drafts.append(params)
        elif "INSERT INTO knowledge.wiki_claim" in sql:
            self.store.claims.append(params)
        elif "INSERT INTO knowledge.claim_dependency" in sql:
            if self.store.dependency_missing:
                raise ValueError("claim dependency must belong to the same release")
            self.store.dependencies.append(params)
        elif "UPDATE knowledge.ingestion_job" in sql:
            if self.store.expire_at_commit:
                self.store.valid_lease = False
            self.row = {"job_id": params[0]} if self.store.valid_lease else None
            if self.row:
                self.store.finished.append((None, "success"))
        else:
            raise AssertionError(f"unexpected SQL: {sql}")

    async def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, store):
        self.store = store

    def transaction(self):
        return FakeTransaction(self.store)

    def cursor(self, **kwargs):
        return FakeCursor(self.store)


class FakeStorage:
    def __init__(self, item):
        self.item = item
        self.row = {"release_id": "published-source", "span_id": item.span_id,
                    "version_id": item.doc_version, "original_text": item.content,
                    "locator": asdict(item.locator), "section_path": list(item.section_path),
                    "source_id": "source-1"}
        self.revoked = False
        self.valid_lease = True
        self.expire_at_commit = False
        self.target_published = False
        self.dependency_missing = False
        self.sql, self.drafts, self.claims, self.dependencies = [], [], [], []
        self.finished, self.reviews, self.queued, self.heartbeats = [], [], [], []
        self.connection = FakeConnection(self)

    async def enqueue_job(self, key, kind, payload, *, max_attempts):
        self.queued.append((key, kind, payload, max_attempts))
        return {"job_id": uuid4(), "kind": kind, "payload": payload}

    async def get_citation(self, release_id, span_id):
        assert release_id == "published-source"
        return None if self.revoked else self.row

    async def heartbeat_job(self, job_id, token, *, lease_seconds):
        self.heartbeats.append((job_id, token))
        if not self.valid_lease:
            raise LeaseLost("secret stale lease")
        return {}

    async def finish_job(self, job_id, token, *, error=None):
        if not self.valid_lease:
            raise LeaseLost("secret stale lease")
        self.finished.append((error, "failed"))
        return {"status": "failed"}

    async def review_wiki_draft(self, release_id, draft_id, *, approved):
        self.reviews.append((release_id, draft_id, approved))


def job(item):
    return {"job_id": uuid4(), "lease_token": uuid4(), "kind": KIND,
            "payload": {"source_release_id": "published-source", "target_release_id": "building-target",
                        "topic": "车型来源", "span_ids": [item.span_id]}}


def service(store, client):
    return WikiJobService(store, client, compiler_model="fake-budgeted-model")


@pytest.mark.asyncio
async def test_enqueue_uses_storage_kind_ids_only_and_single_attempt_by_default():
    item = evidence()
    store = FakeStorage(item)
    await service(store, FakeClient(item)).enqueue("request-1", source_release_id="published-source",
        target_release_id="building-target", topic="车型", span_ids=[item.span_id])
    key, kind, payload, attempts = store.queued[0]
    assert key == "request-1" and kind == KIND and attempts == 1
    assert set(payload) == {"source_release_id", "target_release_id", "topic", "span_ids"}
    assert item.content not in str(payload) and "api_key" not in payload


@pytest.mark.asyncio
async def test_success_persists_draft_claim_dependency_and_never_auto_approves():
    item = evidence()
    store, client = FakeStorage(item), FakeClient(item)
    queued = job(item)
    result = await service(store, client).process_claimed(queued)
    assert result.status == "succeeded"
    assert len(store.drafts) == len(store.claims) == len(store.dependencies) == 1
    assert result.draft_id == "wiki-job-" + str(queued["job_id"])
    assert store.drafts[0][0] == "building-target"
    assert store.claims[0][3] == item.content
    assert store.dependencies[0][2:] == (item.span_id, item.doc_version)
    conditions = store.claims[0][4].obj
    assert conditions["timeless"] is False and conditions["requires_fresh_source"] is True
    assert conditions["live_price_or_inventory"] == "use_business_tool"
    assert "实时业务工具" in store.drafts[0][3]
    assert store.reviews == []
    assert not any("activate" in sql or "approved" in sql for sql in store.sql)
    assert store.heartbeats == [(queued["job_id"], queued["lease_token"])] * 2


@pytest.mark.asyncio
async def test_no_available_source_never_calls_client_or_writes_draft():
    item = evidence()
    store, client = FakeStorage(item), FakeClient(item)
    store.revoked = True
    result = await service(store, client).process_claimed(job(item))
    assert result.error_code == "wiki_source_unavailable"
    assert client.calls == 0 and store.drafts == []
    assert store.finished == [("wiki_source_unavailable", "failed")]


@pytest.mark.asyncio
async def test_revoked_dependency_during_model_discards_entire_compilation():
    item = evidence()
    store = FakeStorage(item)
    client = FakeClient(item, callback=lambda: setattr(store, "revoked", True))
    result = await service(store, client).process_claimed(job(item))
    assert result.error_code == "wiki_source_unavailable"
    assert store.drafts == store.claims == store.dependencies == []


@pytest.mark.asyncio
async def test_model_failure_never_persists_or_returns_provider_secret():
    item = evidence()
    store = FakeStorage(item)
    result = await service(store, FakeClient(item, fail=True)).process_claimed(job(item))
    assert result.error_code == "wiki_model_failed"
    assert store.finished == [("wiki_model_failed", "failed")]
    assert "SECRET" not in repr(result) + repr(store.finished)
    assert store.drafts == []


@pytest.mark.asyncio
@pytest.mark.parametrize("when", ["before", "during-model", "final-update"])
async def test_lease_loss_fences_all_persistence_and_completion(when):
    item = evidence()
    store = FakeStorage(item)
    client = FakeClient(item)
    if when == "before":
        store.valid_lease = False
    elif when == "during-model":
        client.callback = lambda: setattr(store, "valid_lease", False)
    else:
        store.expire_at_commit = True
    result = await service(store, client).process_claimed(job(item))
    assert result.status == "lease_lost" and result.error_code == "lease_lost"
    assert store.drafts == store.claims == store.dependencies == []
    assert store.finished == []
    assert client.calls == int(when != "before")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_target", ["published", "missing-dependency"])
async def test_schema_build_constraints_fail_atomically_without_partial_draft(bad_target):
    item = evidence()
    store = FakeStorage(item)
    store.target_published = bad_target == "published"
    store.dependency_missing = bad_target == "missing-dependency"
    result = await service(store, FakeClient(item)).process_claimed(job(item))
    assert result.status == "failed"
    assert store.drafts == store.claims == store.dependencies == []
    assert store.reviews == []


@pytest.mark.asyncio
async def test_target_failure_after_model_rolls_back_draft_and_claims():
    item = evidence()
    store = FakeStorage(item)
    client = FakeClient(item, callback=lambda: setattr(store, "dependency_missing", True))
    result = await service(store, client).process_claimed(job(item))
    assert result.status == "failed" and client.calls == 1
    assert store.drafts == store.claims == store.dependencies == []


@pytest.mark.asyncio
async def test_revocation_inside_persistence_transaction_blocks_draft():
    item = evidence()
    store = FakeStorage(item)
    compiler = service(store, FakeClient(item))
    persist = compiler._persist
    async def revoke_before_persist(*args):
        store.revoked = True
        return await persist(*args)
    compiler._persist = revoke_before_persist
    result = await compiler.process_claimed(job(item))
    assert result.error_code == "wiki_source_unavailable"
    assert store.drafts == store.claims == store.dependencies == []


@pytest.mark.asyncio
async def test_persistent_wiki_cannot_strip_price_or_inventory_conditions():
    item = evidence()
    store = FakeStorage(item)
    result = await service(store, FakeClient(item, partial=True)).process_claimed(job(item))
    assert result.error_code == "wiki_invalid_evidence_or_output"
    assert store.drafts == []


@pytest.mark.asyncio
async def test_explicit_review_is_separate_and_only_delegates_manual_decision():
    item = evidence()
    store = FakeStorage(item)
    compiler = service(store, FakeClient(item))
    assert store.reviews == []
    await compiler.review("building-target", "draft-id", approved=False)
    assert store.reviews == [("building-target", "draft-id", False)]
    assert not hasattr(compiler, "publish")


@pytest.mark.asyncio
async def test_unknown_kind_is_not_claimed_or_finished_by_wiki_service():
    item = evidence()
    store = FakeStorage(item)
    claimed = {**job(item), "kind": "ingest"}
    with pytest.raises(ValueError):
        await service(store, FakeClient(item)).process_claimed(claimed)
    assert store.finished == [] and store.heartbeats == []


@pytest.mark.asyncio
async def test_malformed_job_payload_is_sanitized_without_model_call():
    item = evidence()
    store, client = FakeStorage(item), FakeClient(item)
    claimed = job(item)
    claimed["payload"]["api_key"] = "sk-secret"
    result = await service(store, client).process_claimed(claimed)
    assert result.error_code == "wiki_invalid_evidence_or_output"
    assert client.calls == 0 and "secret" not in repr(result) + repr(store.finished)


@pytest.mark.parametrize("changes", [
    {"span_ids": []}, {"target_release_id": "published-source"},
    {"span_ids": ["0" * 64, "0" * 64]}, {"topic": " "},
])
def test_request_requires_nonempty_unique_evidence_and_distinct_target(changes):
    payload = {**job(evidence())["payload"], **changes}
    with pytest.raises(ValueError):
        WikiJobRequest.model_validate(payload).check_request()
