-- psql18 variables receive secrets from environment; no password in code/argv.
-- Bootstrap phase creates roles before schema.sql references them. Final phase
-- reapplies this file with dpr_role_bootstrap_only=false to grant object access.
\set ON_ERROR_STOP on
\set ECHO none
\getenv app_user_password DPR_APP_USER_PASSWORD
\getenv analyst_user_password DPR_ANALYST_USER_PASSWORD
\getenv auditor_user_password DPR_AUDITOR_USER_PASSWORD
\getenv backup_user_password DPR_BACKUP_USER_PASSWORD
\getenv admin_user_password DPR_ADMIN_USER_PASSWORD
\getenv migration_user_password DPR_MIGRATION_USER_PASSWORD
\getenv scanner_user_password DPR_SCANNER_USER_PASSWORD
\if :{?app_user_password}
\else
  \echo Required role password environment is missing
  \quit 3
\endif
\if :{?analyst_user_password}
\else
  \quit 3
\endif
\if :{?auditor_user_password}
\else
  \quit 3
\endif
\if :{?backup_user_password}
\else
  \quit 3
\endif
\if :{?admin_user_password}
\else
  \quit 3
\endif
\if :{?migration_user_password}
\else
  \quit 3
\endif
\if :{?scanner_user_password}
\else
  \quit 3
\endif

DO $$
BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN ('schema_owner','app_user','analyst_user','auditor_user','backup_user','admin_user','migration_user','scanner_user')
        AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
      OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member IN (SELECT oid FROM pg_roles WHERE rolname IN
        ('schema_owner','app_user','analyst_user','auditor_user','backup_user','admin_user','migration_user','scanner_user')))
    THEN RAISE EXCEPTION 'Existing service role has unsafe attributes or memberships'; END IF;
END $$;

SELECT 'CREATE ROLE schema_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'
 WHERE NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='schema_owner')
\gexec
SELECT format('CREATE ROLE app_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L', :'app_user_password')
 WHERE NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='app_user')
\gexec
SELECT format('CREATE ROLE analyst_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L', :'analyst_user_password')
 WHERE NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='analyst_user')
\gexec
SELECT format('CREATE ROLE auditor_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L', :'auditor_user_password')
 WHERE NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='auditor_user')
\gexec
SELECT format('CREATE ROLE backup_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L', :'backup_user_password')
 WHERE NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='backup_user')
\gexec
SELECT format('CREATE ROLE admin_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L', :'admin_user_password')
 WHERE NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='admin_user')
\gexec
SELECT format('CREATE ROLE migration_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L', :'migration_user_password')
 WHERE NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='migration_user')
\gexec
SELECT format('CREATE ROLE scanner_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L', :'scanner_user_password')
 WHERE NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='scanner_user')
\gexec

ALTER ROLE schema_owner NOLOGIN NOINHERIT;
ALTER ROLE app_user LOGIN NOINHERIT NOBYPASSRLS;
ALTER ROLE analyst_user LOGIN NOINHERIT NOBYPASSRLS;
ALTER ROLE auditor_user LOGIN NOINHERIT NOBYPASSRLS;
ALTER ROLE backup_user LOGIN NOINHERIT NOBYPASSRLS;
ALTER ROLE admin_user LOGIN NOINHERIT NOBYPASSRLS;
ALTER ROLE migration_user LOGIN NOINHERIT NOBYPASSRLS;
ALTER ROLE scanner_user LOGIN NOINHERIT NOBYPASSRLS;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM app_user,analyst_user,auditor_user,backup_user,admin_user,migration_user,scanner_user;
GRANT USAGE,CREATE ON SCHEMA public TO schema_owner;
GRANT USAGE ON SCHEMA public TO app_user,analyst_user,auditor_user,backup_user,admin_user,migration_user,scanner_user;
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database())
\gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM app_user,analyst_user,auditor_user,backup_user,admin_user,migration_user,scanner_user', current_database())
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO app_user,analyst_user,auditor_user,backup_user,admin_user,migration_user,scanner_user', current_database())
\gexec
ALTER DEFAULT PRIVILEGES FOR ROLE schema_owner IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE schema_owner IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC;
-- Global function default must be revoked: a per-schema revoke cannot cancel it.
ALTER DEFAULT PRIVILEGES FOR ROLE schema_owner REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE schema_owner IN SCHEMA public GRANT SELECT ON TABLES TO backup_user;
ALTER DEFAULT PRIVILEGES FOR ROLE schema_owner IN SCHEMA public GRANT SELECT ON SEQUENCES TO backup_user;

\if :dpr_role_bootstrap_only
\else
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_user,analyst_user,auditor_user,backup_user,admin_user,migration_user,scanner_user;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM app_user,analyst_user,auditor_user,backup_user,admin_user,migration_user,scanner_user;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM app_user,analyst_user,auditor_user,backup_user,admin_user,migration_user,scanner_user;
GRANT SELECT,INSERT,UPDATE ON public.anggota_protected,public.app_users TO app_user;
GRANT SELECT ON public.access_scope TO app_user;
GRANT INSERT(action,anggota_id,field_class,decision,request_id) ON public.audit_log TO app_user,migration_user;
GRANT USAGE ON SEQUENCE public.audit_log_event_id_seq TO app_user,migration_user;
GRANT EXECUTE ON FUNCTION public.request_principal() TO app_user;
GRANT SELECT ON public.analyst_summary TO analyst_user;
GRANT EXECUTE ON FUNCTION public.analyst_age_summary() TO analyst_user;
GRANT SELECT ON public.audit_log TO auditor_user;
GRANT SELECT ON public.anggota_protected,public.app_users,public.access_scope,public.audit_log,public.analyst_view,public.analyst_summary TO backup_user;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO backup_user;
GRANT SELECT,INSERT,UPDATE,DELETE ON public.app_users,public.access_scope TO admin_user;
GRANT SELECT ON public.audit_log TO admin_user;
GRANT USAGE ON SEQUENCE public.access_scope_scope_id_seq TO admin_user;
GRANT SELECT,INSERT,UPDATE ON public.anggota_protected TO migration_user;
GRANT SELECT,INSERT,UPDATE ON public.migration_jobs TO migration_user;
GRANT SELECT ON public.migration_jobs TO backup_user;
GRANT SELECT ON public.anggota_protected,public.analyst_view TO scanner_user;
\endif
