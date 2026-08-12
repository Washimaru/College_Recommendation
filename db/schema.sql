-- UniMatch schema. Owned by the Python side (schema owner = recommendation-service).
-- Applied on first init of an empty Postgres volume via
-- docker-entrypoint-initdb.d. To re-apply after an edit:
--   docker compose down -v && docker compose up -d db

-- Contract v2.0.0. Admissions figures are NULLable by design: a value is either
-- observed from a citable source or absent. Nothing is derived from another
-- field and stored as if independent. `provenance` records the origin of each.
CREATE TABLE IF NOT EXISTS universities (
    id              TEXT PRIMARY KEY,
    unitid          TEXT,                    -- federal IPEDS id where matched; US only
    name            TEXT        NOT NULL,
    country         TEXT        NOT NULL,
    location        TEXT        NOT NULL,
    region          TEXT        NOT NULL CHECK (region IN ('Northeast','South','West','Midwest','International')),
    setting         TEXT        NOT NULL CHECK (setting IN ('urban','suburban','rural')),
    type            TEXT        NOT NULL CHECK (type IN ('Public','Private')),
    avg_gpa         NUMERIC(3,2) NOT NULL CHECK (avg_gpa >= 0 AND avg_gpa <= 4.0),
    avg_sat         INTEGER     CHECK (avg_sat BETWEEN 400 AND 1600),
    acceptance_rate NUMERIC(4,3) CHECK (acceptance_rate >= 0 AND acceptance_rate <= 1),
    net_price       NUMERIC(9,2) CHECK (net_price >= 0),   -- cost after aid
    sticker_tuition NUMERIC(9,2) CHECK (sticker_tuition >= 0),   -- out-of-state
    tuition_in_state NUMERIC(9,2) CHECK (tuition_in_state >= 0),  -- US only; NULL elsewhere
    -- Share of degrees actually awarded, by 2-digit CIP family. NULL means
    -- unmeasured; '[]' means measured and awarding none of them, which is the
    -- only basis on which "this school does not offer X" can be said.
    programs        JSONB,
    enrollment      INTEGER     CHECK (enrollment >= 0),   -- undergraduate only
    size            TEXT        NOT NULL CHECK (size IN ('small','medium','large')),
    majors          JSONB       NOT NULL DEFAULT '[]'::jsonb,
    culture         JSONB       NOT NULL,    -- required: drives 18% of the score
    population      JSONB,                    -- absent for non-US schools
    url             TEXT,
    net_price_calculator_url TEXT,
    details         JSONB,                    -- curated profile; NULL when none exists
    provenance      JSONB       NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_universities_size ON universities (size);
CREATE INDEX IF NOT EXISTS idx_universities_location ON universities (location);
CREATE INDEX IF NOT EXISTS idx_universities_country ON universities (country);
CREATE INDEX IF NOT EXISTS idx_universities_region ON universities (region);

CREATE TABLE IF NOT EXISTS recommendations (
    id          BIGSERIAL PRIMARY KEY,
    profile     JSONB       NOT NULL,
    results     JSONB       NOT NULL,
    confidence  NUMERIC(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    stop_reason TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recommendations_created_at ON recommendations (created_at);
