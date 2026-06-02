-- Runs automatically the first time the postgres container initializes an
-- empty data directory (mounted at /docker-entrypoint-initdb.d/).
-- Image: pgvector/pgvector:pg16 (the vector extension is preinstalled).

-- Enable the pgvector extension for storing/querying embeddings.
CREATE EXTENSION IF NOT EXISTS vector;

-- Example schema for a RAG document store. Uncomment and set the embedding
-- dimension to match your model (e.g. 1536 for text-embedding-3-small).
-- CREATE TABLE IF NOT EXISTS documents (
--     id         BIGSERIAL PRIMARY KEY,
--     content    TEXT        NOT NULL,
--     embedding  VECTOR(1536),
--     created_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- );
