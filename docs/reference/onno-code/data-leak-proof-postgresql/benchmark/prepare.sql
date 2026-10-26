DROP TABLE IF EXISTS migration_control.benchmark_ids;
CREATE TABLE migration_control.benchmark_ids AS
SELECT row_number() OVER (ORDER BY customer_id) AS benchmark_id,
       customer_id, tenant_id
FROM protected_v2.customers_secure;
CREATE UNIQUE INDEX benchmark_ids_pk
ON migration_control.benchmark_ids(benchmark_id);
ANALYZE migration_control.benchmark_ids;

