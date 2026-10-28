-- ACL-only upgrade; run inside one transaction as the provisioning administrator.
-- No role/password changes and no writes to member/application tables.
DO $guard$
BEGIN
    IF current_setting('server_version_num')::int / 10000 <> 18
       OR current_database() !~ '^(protected_(734|100k|1m)|dpr_restore_[0-9a-f]{32})$'
    THEN RAISE EXCEPTION 'Analyst upgrade requires an approved protected PG18 target'; END IF;
    IF (SELECT pg_get_userbyid(relowner) FROM pg_class
        WHERE oid='public.anggota_protected'::regclass) IS DISTINCT FROM 'schema_owner'
       OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname='analyst_user'
          AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication))
       OR EXISTS (SELECT 1 FROM pg_auth_members
          WHERE member=(SELECT oid FROM pg_roles WHERE rolname='analyst_user'))
    THEN RAISE EXCEPTION 'Unsafe analyst ownership or role'; END IF;
END $guard$;

SET LOCAL ROLE schema_owner;
SET LOCAL search_path = pg_catalog, public;

-- Independent one-dimensional marginals, never a projection of member records.
-- Owner rights are deliberate: FORCE RLS allows schema_owner to read all members.
CREATE OR REPLACE VIEW public.analyst_summary
WITH (security_barrier=true, security_invoker=false) AS
    SELECT 'jenis_kelamin'::text AS dimension, jenis_kelamin::text AS value,
           count(*) AS anggota_count
    FROM public.anggota_protected GROUP BY jenis_kelamin HAVING count(*) >= 5
    UNION ALL
    SELECT 'pekerjaan_terakhir', pekerjaan_terakhir::text, count(*)
    FROM public.anggota_protected GROUP BY pekerjaan_terakhir HAVING count(*) >= 5
    UNION ALL
    SELECT 'nama_kppn', nama_kppn::text, count(*)
    FROM public.anggota_protected GROUP BY nama_kppn HAVING count(*) >= 5
    UNION ALL
    SELECT 'nama_bank', nama_bank::text, count(*)
    FROM public.anggota_protected GROUP BY nama_bank HAVING count(*) >= 5
    UNION ALL
    SELECT 'age_band', age_band::text, count(*)
    FROM public.anggota_protected GROUP BY age_band HAVING count(*) >= 5;

-- Preserve the old function signature, but close its unsuppressed GROUP BY path.
CREATE OR REPLACE FUNCTION public.analyst_age_summary()
RETURNS TABLE(age_band varchar(10), anggota_count bigint)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
    SELECT value::varchar(10), anggota_count FROM public.analyst_summary
    WHERE dimension='age_band' ORDER BY value;
$$;
RESET ROLE;

-- Remove all analyst table privileges, including historical column-level grants.
-- Other roles' ACLs, application sessions, sequence state and LOGIN are untouched.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM analyst_user;
DO $columns$
DECLARE object record;
BEGIN
    FOR object IN
        SELECT c.relname, string_agg(quote_ident(a.attname), ',' ORDER BY a.attnum) AS columns
        FROM pg_class c JOIN pg_attribute a ON a.attrelid=c.oid
        WHERE c.relnamespace='public'::regnamespace AND c.relkind IN ('r','p','v','f')
          AND a.attnum>0 AND NOT a.attisdropped
        GROUP BY c.oid,c.relname
    LOOP
        EXECUTE format('REVOKE ALL PRIVILEGES (%s) ON public.%I FROM analyst_user',
                       object.columns,object.relname);
    END LOOP;
END $columns$;
REVOKE ALL ON public.analyst_view,public.anggota_protected,public.analyst_summary FROM PUBLIC;
REVOKE ALL ON FUNCTION public.analyst_age_summary() FROM PUBLIC;
GRANT SELECT ON public.analyst_summary TO analyst_user,backup_user;
GRANT EXECUTE ON FUNCTION public.analyst_age_summary() TO analyst_user;

-- Fail closed if PUBLIC/another inherited path exposes any other public relation.
DO $acl$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class c
        WHERE c.relnamespace='public'::regnamespace AND c.relkind IN ('r','p','v','m','f')
          AND c.oid<>'public.analyst_summary'::regclass
          AND (has_table_privilege('analyst_user',c.oid,'SELECT')
               OR has_any_column_privilege('analyst_user',c.oid,'SELECT')))
    THEN RAISE EXCEPTION 'Analyst still has a per-record read path'; END IF;
END $acl$;
