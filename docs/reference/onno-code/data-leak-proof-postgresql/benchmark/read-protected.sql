\set benchmark_id random(1, :customer_count)
SELECT customer.customer_id, customer.email_payload, customer.phone_payload
FROM migration_control.benchmark_ids AS sample
JOIN protected_v2.customers_secure AS customer
  ON customer.customer_id = sample.customer_id
WHERE sample.benchmark_id = :benchmark_id;

