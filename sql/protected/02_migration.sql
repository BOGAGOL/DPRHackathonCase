-- Metadata only: no DEK, source values, token, or per-cell hashes.
SET LOCAL ROLE schema_owner;
CREATE TABLE IF NOT EXISTS public.migration_jobs (
    job_id smallint PRIMARY KEY CHECK (job_id=1),
    source_database text NOT NULL CHECK (source_database IN ('postgres','baseline_100k')),
    source_identity text NOT NULL,
    profile_sha256 text NOT NULL CHECK (profile_sha256 ~ '^[0-9a-f]{64}$'),
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    source_rows bigint NOT NULL CHECK (source_rows>=0),
    migrated_rows bigint NOT NULL DEFAULT 0 CHECK (migrated_rows>=0 AND migrated_rows<=source_rows),
    last_legacy_id bigint,
    batch_count bigint NOT NULL DEFAULT 0 CHECK (batch_count>=0),
    status text NOT NULL CHECK (status IN ('running','paused','validating','validated')),
    started_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    validated_at timestamptz
);
REVOKE ALL ON public.migration_jobs FROM PUBLIC;
RESET ROLE;
