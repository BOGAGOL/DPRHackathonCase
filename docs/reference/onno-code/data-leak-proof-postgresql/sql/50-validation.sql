\set ON_ERROR_STOP on

SELECT
  (SELECT count(*) FROM lab_v1.customers) AS plaintext_rows,
  (SELECT count(*) FROM protected_v2.customers_secure) AS protected_rows;

SELECT c.customer_id AS not_migrated
FROM lab_v1.customers AS c
LEFT JOIN protected_v2.customers_secure AS p
  ON p.source_customer_id = c.customer_id
WHERE p.source_customer_id IS NULL
ORDER BY c.customer_id
LIMIT 100;

SELECT source_customer_id, count(*) AS copies
FROM protected_v2.customers_secure
GROUP BY source_customer_id
HAVING count(*) > 1;

SELECT
  count(*) FILTER (WHERE email_payload IS NULL) AS missing_email,
  count(*) FILTER (WHERE email_bidx IS NULL) AS missing_email_index,
  count(*) FILTER (WHERE key_version IS NULL) AS missing_key_version
FROM protected_v2.customers_secure;

SELECT protection_version, key_version, count(*) AS records
FROM protected_v2.customers_secure
GROUP BY protection_version, key_version
ORDER BY protection_version, key_version;

SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls
FROM pg_roles
WHERE rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls
ORDER BY rolname;

