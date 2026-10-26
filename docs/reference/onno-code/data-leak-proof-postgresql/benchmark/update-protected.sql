\set benchmark_id random(1, :customer_count)
BEGIN;
UPDATE protected_v2.customers_secure AS customer
SET updated_at = clock_timestamp()
FROM migration_control.benchmark_ids AS sample
WHERE sample.benchmark_id = :benchmark_id
  AND customer.customer_id = sample.customer_id;
COMMIT;

