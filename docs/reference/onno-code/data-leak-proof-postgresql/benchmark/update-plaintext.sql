\set customer_id random(1, :customer_count)
BEGIN;
UPDATE lab_v1.customers
SET updated_at = clock_timestamp()
WHERE customer_id = :customer_id;
COMMIT;

