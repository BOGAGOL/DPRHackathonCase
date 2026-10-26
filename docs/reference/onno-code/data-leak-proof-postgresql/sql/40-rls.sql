\set ON_ERROR_STOP on

ALTER TABLE protected_v2.customers_secure ENABLE ROW LEVEL SECURITY;
ALTER TABLE protected_v2.customers_secure FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS customers_tenant_policy ON protected_v2.customers_secure;
CREATE POLICY customers_tenant_policy
ON protected_v2.customers_secure
FOR ALL TO app_privileges
USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE protected_v2.transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE protected_v2.transactions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS transactions_tenant_policy ON protected_v2.transactions;
CREATE POLICY transactions_tenant_policy
ON protected_v2.transactions
FOR ALL TO app_privileges
USING (
  EXISTS (
    SELECT 1 FROM protected_v2.customers_secure AS customer
    WHERE customer.customer_id = transactions.customer_id
  )
)
WITH CHECK (
  EXISTS (
    SELECT 1 FROM protected_v2.customers_secure AS customer
    WHERE customer.customer_id = transactions.customer_id
  )
);

