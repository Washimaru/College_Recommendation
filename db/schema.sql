-- UniMatch schema. Owned by the Python side (schema owner = recommendation-service).
-- Applied on first init of an empty Postgres volume via
-- docker-entrypoint-initdb.d. To re-apply after an edit:
--   docker compose down -v && docker compose up -d db

CREATE TABLE IF NOT EXISTS universities (
    id              TEXT PRIMARY KEY,
    name            TEXT        NOT NULL,
    avg_gpa         NUMERIC(3,2) NOT NULL CHECK (avg_gpa >= 0 AND avg_gpa <= 4.0),
    avg_sat         INTEGER     NOT NULL CHECK (avg_sat BETWEEN 400 AND 1600),
    acceptance_rate NUMERIC(4,3) NOT NULL CHECK (acceptance_rate >= 0 AND acceptance_rate <= 1),
    tuition         NUMERIC(9,2) NOT NULL CHECK (tuition >= 0),
    size            TEXT        NOT NULL CHECK (size IN ('small','medium','large')),
    location        TEXT        NOT NULL,
    majors          JSONB       NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_universities_size ON universities (size);
CREATE INDEX IF NOT EXISTS idx_universities_location ON universities (location);

CREATE TABLE IF NOT EXISTS recommendations (
    id          BIGSERIAL PRIMARY KEY,
    profile     JSONB       NOT NULL,
    results     JSONB       NOT NULL,
    confidence  NUMERIC(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    stop_reason TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recommendations_created_at ON recommendations (created_at);
