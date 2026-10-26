#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_ADMIN_USER:?required}"
: "${POSTGRES_DB:?required}"
: "${APP_DB_USER:?required}"
: "${APP_DB_PASSWORD:?required}"
: "${MIGRATOR_DB_USER:?required}"
: "${MIGRATOR_DB_PASSWORD:?required}"
: "${EXPORTER_DB_USER:?required}"
: "${EXPORTER_DB_PASSWORD:?required}"

psql --set=ON_ERROR_STOP=1 \
  --username "$POSTGRES_ADMIN_USER" \
  --dbname "$POSTGRES_DB" \
  --set=app_user="$APP_DB_USER" \
  --set=app_password="$APP_DB_PASSWORD" \
  --set=migrator_user="$MIGRATOR_DB_USER" \
  --set=migrator_password="$MIGRATOR_DB_PASSWORD" \
  --set=exporter_user="$EXPORTER_DB_USER" \
  --set=exporter_password="$EXPORTER_DB_PASSWORD" <<'SQL'
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database()) \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA lab_v1, protected_v2, migration_control FROM PUBLIC;

CREATE ROLE app_privileges NOLOGIN;
CREATE ROLE migration_privileges NOLOGIN;
CREATE ROLE monitor_privileges NOLOGIN;

SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'app_user', :'app_password'
) \gexec

SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'migrator_user', :'migrator_password'
) \gexec

SELECT format(
  'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'exporter_user', :'exporter_password'
) \gexec

SELECT format('GRANT app_privileges TO %I', :'app_user') \gexec
SELECT format('GRANT migration_privileges TO %I', :'migrator_user') \gexec
SELECT format('GRANT pg_monitor TO %I', :'exporter_user') \gexec

GRANT USAGE ON SCHEMA protected_v2 TO app_privileges;
GRANT SELECT, INSERT, UPDATE ON protected_v2.customers_secure, protected_v2.transactions TO app_privileges;
GRANT USAGE ON SCHEMA lab_v1, protected_v2, migration_control TO migration_privileges;
GRANT SELECT ON lab_v1.customers, lab_v1.transactions TO migration_privileges;
GRANT SELECT, INSERT, UPDATE ON protected_v2.customers_secure, protected_v2.transactions TO migration_privileges;
GRANT SELECT, UPDATE ON migration_control.jobs TO migration_privileges;
SQL
