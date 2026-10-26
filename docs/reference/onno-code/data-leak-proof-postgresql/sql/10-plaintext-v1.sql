\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS lab_v1.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL,
    full_name text NOT NULL,
    email text NOT NULL,
    phone text,
    national_id text,
    password_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS customers_v1_tenant_email_uq
ON lab_v1.customers (tenant_id, lower(email));

CREATE TABLE IF NOT EXISTS lab_v1.transactions (
    transaction_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES lab_v1.customers(customer_id),
    amount numeric(18,2) NOT NULL,
    currency char(3) NOT NULL,
    description text,
    created_at timestamptz NOT NULL DEFAULT now()
);

