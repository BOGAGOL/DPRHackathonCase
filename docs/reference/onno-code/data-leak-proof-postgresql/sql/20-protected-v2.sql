\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS protected_v2.customers_secure (
    customer_id uuid PRIMARY KEY,
    source_customer_id bigint UNIQUE,
    tenant_id uuid NOT NULL,
    full_name_token text,
    email_payload bytea NOT NULL,
    email_bidx bytea NOT NULL,
    phone_payload bytea,
    phone_bidx bytea,
    national_id_payload bytea,
    password_hash text NOT NULL,
    protection_version smallint NOT NULL,
    key_version integer NOT NULL,
    migrated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (octet_length(email_bidx) = 32),
    CHECK (phone_bidx IS NULL OR octet_length(phone_bidx) = 32),
    CHECK (protection_version > 0),
    CHECK (key_version > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS customers_v2_tenant_email_uq
ON protected_v2.customers_secure (tenant_id, email_bidx);

CREATE INDEX IF NOT EXISTS customers_v2_phone_idx
ON protected_v2.customers_secure (tenant_id, phone_bidx)
WHERE phone_bidx IS NOT NULL;

CREATE TABLE IF NOT EXISTS protected_v2.transactions (
    transaction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id uuid NOT NULL REFERENCES protected_v2.customers_secure(customer_id),
    amount numeric(18,2) NOT NULL,
    currency char(3) NOT NULL,
    description_payload bytea,
    key_version integer NOT NULL CHECK (key_version > 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS migration_control.jobs (
    job_name text PRIMARY KEY,
    paused boolean NOT NULL DEFAULT true,
    batch_size integer NOT NULL DEFAULT 100 CHECK (batch_size BETWEEN 1 AND 10000),
    target_key_version integer NOT NULL,
    rows_completed bigint NOT NULL DEFAULT 0,
    last_completed_id bigint,
    last_error_code text,
    started_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO migration_control.jobs (job_name, paused, batch_size, target_key_version)
VALUES ('customers_v1_to_v2', true, 100, 1)
ON CONFLICT (job_name) DO NOTHING;

