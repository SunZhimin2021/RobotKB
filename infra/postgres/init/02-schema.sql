-- ── documents ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id                uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
    title             text        NOT NULL,
    category          text        NOT NULL,
    source_tier       text        NOT NULL,
    applicable_chips  text[]      NOT NULL DEFAULT '{}',
    applicable_boards text[]      NOT NULL DEFAULT '{}',
    ros_versions      text[]      NOT NULL DEFAULT '{}',
    tags              text[]      NOT NULL DEFAULT '{}',
    doc_version       text        NOT NULL,
    status            text        NOT NULL DEFAULT 'pending',
    content_hash      text        NOT NULL,
    chunk_count       int         NOT NULL DEFAULT 0,
    author            text,
    vendor            text,
    valid_until       timestamptz,
    superseded_by     uuid        REFERENCES documents(id),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT documents_content_hash_key UNIQUE (content_hash)
);

CREATE INDEX IF NOT EXISTS idx_documents_status
    ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_applicable_chips
    ON documents USING GIN(applicable_chips);
CREATE INDEX IF NOT EXISTS idx_documents_applicable_boards
    ON documents USING GIN(applicable_boards);
CREATE INDEX IF NOT EXISTS idx_documents_category_status
    ON documents(category, status);

-- ── chunks ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks (
    id                uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id       uuid        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content           text        NOT NULL,
    page              int,
    section           text,
    applicable_chips  text[]      NOT NULL DEFAULT '{}',
    applicable_boards text[]      NOT NULL DEFAULT '{}',
    ros_versions      text[]      NOT NULL DEFAULT '{}',
    source_tier       text,
    status            text        NOT NULL DEFAULT 'pending',
    embedding         vector(1024),
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunks_document_id
    ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_status
    ON chunks(status);
CREATE INDEX IF NOT EXISTS idx_chunks_applicable_chips
    ON chunks USING GIN(applicable_chips);
CREATE INDEX IF NOT EXISTS idx_chunks_applicable_boards
    ON chunks USING GIN(applicable_boards);

-- Vector index: create AFTER data is loaded (ivfflat requires rows for clustering).
-- Run manually once you have ≥ 1000 chunks:
--   CREATE INDEX idx_chunks_embedding
--     ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ── outbox ────────────────────────────────────────────────────────────────────
-- Events written atomically with the originating DB write; worker consumes
-- asynchronously to sync Meilisearch and Neo4j.
CREATE TABLE IF NOT EXISTS outbox (
    id           bigserial   PRIMARY KEY,
    event_type   text        NOT NULL,
    payload      jsonb       NOT NULL,
    status       text        NOT NULL DEFAULT 'pending',
    retry_count  int         NOT NULL DEFAULT 0,
    created_at   timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_outbox_status_created
    ON outbox(status, created_at);

-- ── dead_letter ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dead_letter (
    id         bigserial   PRIMARY KEY,
    outbox_id  bigint,
    error      text,
    payload    jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ── updated_at trigger ────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'documents_updated_at'
    ) THEN
        CREATE TRIGGER documents_updated_at
            BEFORE UPDATE ON documents
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;
