-- Run as an administrator connected to the target database.
-- psql command substitution captures stdout into the variable, never the terminal.
-- getpass refuses echoing fallback; activate the Python environment first.
-- No default privileges: future tables require an explicit reviewed grant.
\set ON_ERROR_STOP on
\set ECHO none
\set VERBOSITY sqlstate
\if :{?scanner_password}
\else
  \set scanner_password `python -c "import getpass,warnings; warnings.simplefilter('error',getpass.GetPassWarning); print(getpass.getpass('Password for scanner_user: '))"`
\endif
BEGIN;
CREATE ROLE scanner_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'scanner_password';
SELECT current_database() AS scanner_database \gset
GRANT CONNECT ON DATABASE :"scanner_database" TO scanner_user;
GRANT USAGE ON SCHEMA public TO scanner_user;
GRANT SELECT ON TABLE public.anggota TO scanner_user;
ALTER ROLE scanner_user SET default_transaction_read_only = on;
COMMIT;
\unset scanner_password
\unset scanner_database
-- PostgreSQL PUBLIC privileges are inherited even with NOINHERIT. The owner must
-- audit PUBLIC grants (including callable SECURITY DEFINER routines and schema
-- CREATE), and revoke unsafe PUBLIC privileges separately before deployment.
