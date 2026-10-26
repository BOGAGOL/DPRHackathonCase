\set customer_id random(1, :customer_count)
SELECT customer_id, email, phone
FROM lab_v1.customers
WHERE customer_id = :customer_id;

