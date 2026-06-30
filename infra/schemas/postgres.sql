-- HairGPT Postgres schema. Apply once after enabling extensions.
-- Idempotent: safe to re-run.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- for gen_random_uuid()

-- Knowledge base chunks
CREATE TABLE IF NOT EXISTS kb_chunks (
  id              BIGSERIAL PRIMARY KEY,
  content         TEXT NOT NULL,
  embedding       VECTOR(768),
  content_tsv     TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  source_type     TEXT NOT NULL,
  source_url      TEXT,
  source_id       TEXT,
  chunk_type      TEXT,
  topic_tags      TEXT[],
  product_refs    TEXT[],
  hair_types      TEXT[],
  version         INT NOT NULL DEFAULT 1,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  metadata        JSONB
);

CREATE INDEX IF NOT EXISTS kb_chunks_embedding_idx ON kb_chunks
  USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS kb_chunks_tsv_idx       ON kb_chunks USING GIN (content_tsv);
CREATE INDEX IF NOT EXISTS kb_chunks_tags_idx      ON kb_chunks USING GIN (topic_tags);
CREATE INDEX IF NOT EXISTS kb_chunks_products_idx  ON kb_chunks USING GIN (product_refs);
CREATE INDEX IF NOT EXISTS kb_chunks_active_type_idx ON kb_chunks (is_active, source_type);

-- Conversations
CREATE TABLE IF NOT EXISTS conversations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id      TEXT NOT NULL,
  customer_id     TEXT,
  started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_activity   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  channel         TEXT NOT NULL DEFAULT 'web',
  page_context    JSONB,
  status          TEXT DEFAULT 'active',
  escalation_ref  TEXT
);
CREATE INDEX IF NOT EXISTS conversations_session_idx  ON conversations (session_id);
CREATE INDEX IF NOT EXISTS conversations_customer_idx ON conversations (customer_id);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
  id              BIGSERIAL PRIMARY KEY,
  conversation_id UUID REFERENCES conversations(id),
  role            TEXT NOT NULL,
  content         TEXT,
  tool_calls      JSONB,
  tool_results    JSONB,
  model           TEXT,
  tokens_in       INT,
  tokens_out      INT,
  latency_ms      INT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS messages_conv_idx ON messages (conversation_id, created_at);

-- Kiosk sessions (brand events)
CREATE TABLE IF NOT EXISTS kiosk_sessions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_name      TEXT NOT NULL DEFAULT 'flipkart_jun2026',
  user_name       TEXT NOT NULL,
  phone           TEXT NOT NULL,
  hair_type       TEXT,
  hair_analysis   JSONB,
  primary_concern TEXT,
  routine_name    TEXT,
  routine_steps   JSONB,
  sampler_given   BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kiosk_phone ON kiosk_sessions (phone);
CREATE INDEX IF NOT EXISTS idx_kiosk_event ON kiosk_sessions (event_name);

-- Feedback
CREATE TABLE IF NOT EXISTS message_feedback (
  message_id      BIGINT REFERENCES messages(id),
  rating          INT,
  reason          TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (message_id)
);
