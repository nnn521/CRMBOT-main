-- RAG v2 is additive and isolated from the application's existing tables.
-- Run through scripts/migrate_knowledge.py (transaction + advisory lock + checksum).
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
CREATE SCHEMA IF NOT EXISTS knowledge;

CREATE TABLE knowledge.source_document (
    source_id text PRIMARY KEY CHECK (btrim(source_id) <> ''),
    doc_id text NOT NULL UNIQUE CHECK (btrim(doc_id) <> ''),
    source_uri text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE knowledge.document_version (
    version_id text PRIMARY KEY CHECK (btrim(version_id) <> ''),
    source_id text NOT NULL REFERENCES knowledge.source_document(source_id),
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    original_content bytea NOT NULL,
    title text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(metadata) = 'object'),
    valid_from timestamptz NOT NULL DEFAULT '-infinity',
    valid_until timestamptz NOT NULL DEFAULT 'infinity',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (version_id, source_id),
    CHECK (valid_from < valid_until)
);
CREATE INDEX document_version_source_idx ON knowledge.document_version(source_id);

CREATE TABLE knowledge.evidence_span (
    span_id text PRIMARY KEY CHECK (btrim(span_id) <> ''),
    version_id text NOT NULL REFERENCES knowledge.document_version(version_id),
    original_text text NOT NULL CHECK (btrim(original_text) <> ''),
    locator jsonb NOT NULL CHECK (jsonb_typeof(locator) = 'object'),
    section_path jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(section_path) = 'array'),
    UNIQUE (span_id, version_id)
);

CREATE TABLE knowledge.knowledge_release (
    release_id text PRIMARY KEY CHECK (btrim(release_id) <> ''),
    status text NOT NULL DEFAULT 'building'
        CHECK (status IN ('building', 'ready', 'published', 'failed')),
    embedding_model text NOT NULL CHECK (btrim(embedding_model) <> ''),
    embedding_revision text NOT NULL CHECK (btrim(embedding_revision) <> ''),
    embedding_dim integer NOT NULL CHECK (embedding_dim BETWEEN 1 AND 16000),
    embedding_normalized boolean NOT NULL,
    distance_metric text NOT NULL CHECK (distance_metric = 'cosine'),
    expected_chunks integer NOT NULL CHECK (expected_chunks > 0),
    corpus_sha256 text NOT NULL CHECK (corpus_sha256 ~ '^[0-9a-f]{64}$'),
    bm25_sha256 text NOT NULL CHECK (bm25_sha256 ~ '^[0-9a-f]{64}$'),
    evaluation jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(evaluation) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    ready_at timestamptz,
    published_at timestamptz
);

-- Deliberately unbounded vector: different releases may use different dimensions.
-- No ANN index: the filtered candidate set is materialized before exact cosine rank.
CREATE TABLE knowledge.retrieval_chunk (
    release_id text NOT NULL REFERENCES knowledge.knowledge_release(release_id),
    chunk_id text NOT NULL CHECK (btrim(chunk_id) <> ''),
    span_id text NOT NULL,
    version_id text NOT NULL,
    content text NOT NULL CHECK (btrim(content) <> ''),
    token_count integer NOT NULL CHECK (token_count > 0),
    embedding public.vector NOT NULL,
    PRIMARY KEY (release_id, chunk_id),
    FOREIGN KEY (span_id, version_id)
        REFERENCES knowledge.evidence_span(span_id, version_id)
);
CREATE INDEX retrieval_chunk_span_idx ON knowledge.retrieval_chunk(span_id, version_id);

-- Shared authenticated corpus only. No tenant/ACL fields pretending to authorize.
CREATE TABLE knowledge.active_release (
    scope text PRIMARY KEY DEFAULT 'shared' CHECK (scope = 'shared'),
    release_id text NOT NULL REFERENCES knowledge.knowledge_release(release_id),
    switched_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

-- Append-only barrier OUTSIDE releases. Switching back never un-revokes a source.
CREATE TABLE knowledge.source_revocation (
    source_id text PRIMARY KEY REFERENCES knowledge.source_document(source_id),
    reason text NOT NULL CHECK (btrim(reason) <> ''),
    revoked_by text NOT NULL CHECK (btrim(revoked_by) <> ''),
    revoked_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE knowledge.wiki_draft (
    release_id text NOT NULL REFERENCES knowledge.knowledge_release(release_id),
    draft_id text NOT NULL CHECK (btrim(draft_id) <> ''),
    title text NOT NULL,
    body text NOT NULL,
    compiler_model text NOT NULL,
    prompt_revision text NOT NULL,
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'rejected')),
    PRIMARY KEY (release_id, draft_id)
);
CREATE TABLE knowledge.wiki_claim (
    release_id text NOT NULL,
    claim_id text NOT NULL CHECK (btrim(claim_id) <> ''),
    draft_id text NOT NULL,
    claim_text text NOT NULL CHECK (btrim(claim_text) <> ''),
    conditions jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(conditions) = 'object'),
    PRIMARY KEY (release_id, claim_id),
    FOREIGN KEY (release_id, draft_id) REFERENCES knowledge.wiki_draft(release_id, draft_id)
);
CREATE TABLE knowledge.claim_dependency (
    release_id text NOT NULL,
    claim_id text NOT NULL,
    span_id text NOT NULL,
    version_id text NOT NULL,
    PRIMARY KEY (release_id, claim_id, span_id),
    FOREIGN KEY (release_id, claim_id) REFERENCES knowledge.wiki_claim(release_id, claim_id),
    FOREIGN KEY (span_id, version_id) REFERENCES knowledge.evidence_span(span_id, version_id)
);
CREATE INDEX claim_dependency_source_idx ON knowledge.claim_dependency(version_id);

CREATE TABLE knowledge.ingestion_job (
    job_id uuid PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE CHECK (btrim(idempotency_key) <> ''),
    kind text NOT NULL CHECK (btrim(kind) <> ''),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts > 0 AND attempts <= max_attempts),
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    lease_owner text,
    lease_token uuid,
    lease_until timestamptz,
    heartbeat_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    CHECK ((status = 'running') =
        (lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_until IS NOT NULL)),
    CHECK (status = 'running' OR
        (lease_owner IS NULL AND lease_token IS NULL AND lease_until IS NULL))
);
CREATE INDEX ingestion_job_claim_idx ON knowledge.ingestion_job(status, available_at, lease_until);

CREATE FUNCTION knowledge.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only; create a new version instead', TG_TABLE_NAME;
END;
$$;
CREATE TRIGGER source_immutable BEFORE UPDATE OR DELETE ON knowledge.source_document
    FOR EACH ROW EXECUTE FUNCTION knowledge.reject_mutation();
CREATE TRIGGER version_immutable BEFORE UPDATE OR DELETE ON knowledge.document_version
    FOR EACH ROW EXECUTE FUNCTION knowledge.reject_mutation();
CREATE TRIGGER span_immutable BEFORE UPDATE OR DELETE ON knowledge.evidence_span
    FOR EACH ROW EXECUTE FUNCTION knowledge.reject_mutation();
CREATE TRIGGER chunk_immutable BEFORE UPDATE OR DELETE ON knowledge.retrieval_chunk
    FOR EACH ROW EXECUTE FUNCTION knowledge.reject_mutation();
CREATE TRIGGER revocation_immutable BEFORE UPDATE OR DELETE ON knowledge.source_revocation
    FOR EACH ROW EXECUTE FUNCTION knowledge.reject_mutation();
CREATE TRIGGER claim_immutable BEFORE UPDATE OR DELETE ON knowledge.wiki_claim
    FOR EACH ROW EXECUTE FUNCTION knowledge.reject_mutation();
CREATE TRIGGER dependency_immutable BEFORE UPDATE OR DELETE ON knowledge.claim_dependency
    FOR EACH ROW EXECUTE FUNCTION knowledge.reject_mutation();

-- The parent lock fences inserts against ready/publish, including concurrent workers.
CREATE FUNCTION knowledge.guard_build_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    manifest knowledge.knowledge_release%ROWTYPE;
BEGIN
    SELECT * INTO manifest FROM knowledge.knowledge_release
        WHERE release_id = NEW.release_id FOR SHARE;
    IF NOT FOUND OR manifest.status <> 'building' THEN
        RAISE EXCEPTION 'release must be building';
    END IF;
    IF TG_TABLE_NAME = 'retrieval_chunk' THEN
        IF public.vector_dims(NEW.embedding) <> manifest.embedding_dim
            OR public.vector_norm(NEW.embedding) = 0 THEN
            RAISE EXCEPTION 'embedding dimension mismatch or zero vector';
        END IF;
        IF manifest.embedding_normalized AND abs(public.vector_norm(NEW.embedding) - 1) > 0.001 THEN
            RAISE EXCEPTION 'embedding must be unit normalized';
        END IF;
    ELSIF TG_TABLE_NAME = 'wiki_draft' THEN
        IF NEW.status <> 'draft' THEN
            RAISE EXCEPTION 'wiki records must start as unreviewed drafts';
        END IF;
    ELSIF TG_TABLE_NAME = 'wiki_claim' THEN
        PERFORM 1 FROM knowledge.wiki_draft d
            WHERE d.release_id = NEW.release_id AND d.draft_id = NEW.draft_id
                AND d.status = 'draft' FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'cannot add claims after a draft review';
        END IF;
    ELSIF TG_TABLE_NAME = 'claim_dependency' THEN
        PERFORM 1 FROM knowledge.wiki_claim claim
            JOIN knowledge.wiki_draft d ON d.release_id = claim.release_id AND d.draft_id = claim.draft_id
            WHERE claim.release_id = NEW.release_id AND claim.claim_id = NEW.claim_id
                AND d.status = 'draft' FOR SHARE OF d;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'cannot change dependencies after a draft review';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM knowledge.retrieval_chunk c
            WHERE c.release_id = NEW.release_id AND c.span_id = NEW.span_id
                AND c.version_id = NEW.version_id) THEN
            RAISE EXCEPTION 'claim dependency must belong to the same release';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER chunk_build_only BEFORE INSERT ON knowledge.retrieval_chunk
    FOR EACH ROW EXECUTE FUNCTION knowledge.guard_build_insert();
CREATE TRIGGER draft_build_only BEFORE INSERT ON knowledge.wiki_draft
    FOR EACH ROW EXECUTE FUNCTION knowledge.guard_build_insert();
CREATE TRIGGER claim_build_only BEFORE INSERT ON knowledge.wiki_claim
    FOR EACH ROW EXECUTE FUNCTION knowledge.guard_build_insert();
CREATE TRIGGER dependency_build_only BEFORE INSERT ON knowledge.claim_dependency
    FOR EACH ROW EXECUTE FUNCTION knowledge.guard_build_insert();

CREATE FUNCTION knowledge.guard_wiki_decision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM knowledge.knowledge_release
        WHERE release_id = OLD.release_id AND status = 'building' FOR SHARE;
    IF NOT FOUND OR OLD.status <> 'draft' OR NEW.status NOT IN ('approved', 'rejected')
        OR (to_jsonb(NEW) - 'status') IS DISTINCT FROM (to_jsonb(OLD) - 'status') THEN
        RAISE EXCEPTION 'only a building wiki draft can receive a review decision';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER draft_decision BEFORE UPDATE ON knowledge.wiki_draft
    FOR EACH ROW EXECUTE FUNCTION knowledge.guard_wiki_decision();
CREATE TRIGGER draft_immutable_delete BEFORE DELETE ON knowledge.wiki_draft
    FOR EACH ROW EXECUTE FUNCTION knowledge.reject_mutation();

CREATE FUNCTION knowledge.guard_release_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'building' OR NEW.ready_at IS NOT NULL OR NEW.published_at IS NOT NULL THEN
            RAISE EXCEPTION 'new releases must start building';
        END IF;
        RETURN NEW;
    END IF;
    IF (to_jsonb(NEW) - ARRAY['status', 'ready_at', 'published_at']) IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['status', 'ready_at', 'published_at']) THEN
        RAISE EXCEPTION 'release manifest is immutable';
    END IF;
    IF OLD.status = 'building' AND NEW.status IN ('ready', 'failed') THEN
        IF NEW.status = 'ready' THEN
            IF (SELECT count(*) FROM knowledge.retrieval_chunk WHERE release_id = OLD.release_id)
                <> OLD.expected_chunks THEN
                RAISE EXCEPTION 'release chunks are incomplete';
            END IF;
            IF EXISTS (SELECT 1 FROM knowledge.wiki_draft d WHERE d.release_id = OLD.release_id
                AND (d.status <> 'approved' OR NOT EXISTS (
                    SELECT 1 FROM knowledge.wiki_claim c WHERE c.release_id = d.release_id
                        AND c.draft_id = d.draft_id))) OR EXISTS (
                SELECT 1 FROM knowledge.wiki_claim c WHERE c.release_id = OLD.release_id
                    AND NOT EXISTS (SELECT 1 FROM knowledge.claim_dependency dep
                        WHERE dep.release_id = c.release_id AND dep.claim_id = c.claim_id)) THEN
                RAISE EXCEPTION 'wiki drafts require reviewed claims and dependencies';
            END IF;
            NEW.ready_at := clock_timestamp();
        END IF;
        NEW.published_at := NULL;
    ELSIF OLD.status = 'ready' AND NEW.status = 'published' THEN
        NEW.ready_at := OLD.ready_at;
        NEW.published_at := clock_timestamp();
    ELSE
        RAISE EXCEPTION 'invalid release state transition: % -> %', OLD.status, NEW.status;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER release_transition BEFORE INSERT OR UPDATE ON knowledge.knowledge_release
    FOR EACH ROW EXECUTE FUNCTION knowledge.guard_release_transition();
CREATE TRIGGER release_immutable_delete BEFORE DELETE ON knowledge.knowledge_release
    FOR EACH ROW EXECUTE FUNCTION knowledge.reject_mutation();

CREATE FUNCTION knowledge.guard_active_release() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM knowledge.knowledge_release
        WHERE release_id = NEW.release_id AND status = 'published' FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'active release must be fully built and published';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER active_published_only BEFORE INSERT OR UPDATE ON knowledge.active_release
    FOR EACH ROW EXECUTE FUNCTION knowledge.guard_active_release();
