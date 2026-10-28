-- Run through python -m infra.protected.apply (roles bootstrap + one transaction).
-- All data objects belong to a NOLOGIN owner, never to the application login.
SET LOCAL ROLE schema_owner;
SET LOCAL search_path = pg_catalog, public;

CREATE TABLE IF NOT EXISTS public.app_users (
    user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username varchar(150) UNIQUE NOT NULL CHECK (length(btrim(username)) > 0),
    password_hash text NOT NULL CHECK (
        password_hash ~ '^\$argon2id\$v=19\$m=[1-9][0-9]*,t=[1-9][0-9]*,p=[1-9][0-9]*\$[A-Za-z0-9+/]+\$[A-Za-z0-9+/]+$'),
    role varchar(32) NOT NULL CHECK (role IN ('operator','privileged_officer','finance_officer','analyst','auditor','anggota')),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.anggota_protected (
    anggota_id uuid PRIMARY KEY DEFAULT gen_random_uuid()
        CHECK (substr(anggota_id::text,15,1) = '4' AND substr(anggota_id::text,20,1) IN ('8','9','a','b')),
    legacy_row_id bigint UNIQUE NOT NULL,
    protection_version smallint NOT NULL CHECK (protection_version = 1),
    dek_pii_wrapped text NOT NULL CHECK (dek_pii_wrapped ~ '^vault:v[1-9][0-9]*:[A-Za-z0-9+/]+={0,2}$'),
    dek_fin_wrapped text NOT NULL CHECK (dek_fin_wrapped ~ '^vault:v[1-9][0-9]*:[A-Za-z0-9+/]+={0,2}$'),
    nama_ct bytea CHECK (octet_length(nama_ct)>=29 AND substring(nama_ct FROM 1 FOR 1)='\x01'::bytea),
    nama_lengkap_ct bytea CHECK (octet_length(nama_lengkap_ct)>=29 AND substring(nama_lengkap_ct FROM 1 FOR 1)='\x01'::bytea),
    nama_tanpa_gelar_ct bytea CHECK (octet_length(nama_tanpa_gelar_ct)>=29 AND substring(nama_tanpa_gelar_ct FROM 1 FOR 1)='\x01'::bytea),
    tempat_lahir_ct bytea CHECK (octet_length(tempat_lahir_ct)>=29 AND substring(tempat_lahir_ct FROM 1 FOR 1)='\x01'::bytea),
    tanggal_lahir_ct bytea CHECK (octet_length(tanggal_lahir_ct)>=29 AND substring(tanggal_lahir_ct FROM 1 FOR 1)='\x01'::bytea),
    tanggal_pernikahan_ct bytea CHECK (octet_length(tanggal_pernikahan_ct)>=29 AND substring(tanggal_pernikahan_ct FROM 1 FOR 1)='\x01'::bytea),
    no_ktp_ct bytea CHECK (octet_length(no_ktp_ct)>=29 AND substring(no_ktp_ct FROM 1 FOR 1)='\x01'::bytea),
    alamat_jakarta_ct bytea CHECK (octet_length(alamat_jakarta_ct)>=29 AND substring(alamat_jakarta_ct FROM 1 FOR 1)='\x01'::bytea),
    alamat_daerah_ct bytea CHECK (octet_length(alamat_daerah_ct)>=29 AND substring(alamat_daerah_ct FROM 1 FOR 1)='\x01'::bytea),
    telpon_jakarta_ct bytea CHECK (octet_length(telpon_jakarta_ct)>=29 AND substring(telpon_jakarta_ct FROM 1 FOR 1)='\x01'::bytea),
    telpon_daerah_ct bytea CHECK (octet_length(telpon_daerah_ct)>=29 AND substring(telpon_daerah_ct FROM 1 FOR 1)='\x01'::bytea),
    handphone_ct bytea CHECK (octet_length(handphone_ct)>=29 AND substring(handphone_ct FROM 1 FOR 1)='\x01'::bytea),
    email_ct bytea CHECK (octet_length(email_ct)>=29 AND substring(email_ct FROM 1 FOR 1)='\x01'::bytea),
    ruangan_ct bytea CHECK (octet_length(ruangan_ct)>=29 AND substring(ruangan_ct FROM 1 FOR 1)='\x01'::bytea),
    status_kawin_ct bytea CHECK (octet_length(status_kawin_ct)>=29 AND substring(status_kawin_ct FROM 1 FOR 1)='\x01'::bytea),
    jumlah_anak_ct bytea CHECK (octet_length(jumlah_anak_ct)>=29 AND substring(jumlah_anak_ct FROM 1 FOR 1)='\x01'::bytea),
    jumlah_tanggungan_ct bytea CHECK (octet_length(jumlah_tanggungan_ct)>=29 AND substring(jumlah_tanggungan_ct FROM 1 FOR 1)='\x01'::bytea),
    jumlah_jiwa_ct bytea CHECK (octet_length(jumlah_jiwa_ct)>=29 AND substring(jumlah_jiwa_ct FROM 1 FOR 1)='\x01'::bytea),
    rekening_ct bytea CHECK (octet_length(rekening_ct)>=29 AND substring(rekening_ct FROM 1 FOR 1)='\x01'::bytea),
    nama_rekening_ct bytea CHECK (octet_length(nama_rekening_ct)>=29 AND substring(nama_rekening_ct FROM 1 FOR 1)='\x01'::bytea),
    npwp_ct bytea CHECK (octet_length(npwp_ct)>=29 AND substring(npwp_ct FROM 1 FOR 1)='\x01'::bytea),
    kode_bank_ct bytea CHECK (octet_length(kode_bank_ct)>=29 AND substring(kode_bank_ct FROM 1 FOR 1)='\x01'::bytea),
    nip_kppn_ct bytea CHECK (octet_length(nip_kppn_ct)>=29 AND substring(nip_kppn_ct FROM 1 FOR 1)='\x01'::bytea),
    pengguna_ct bytea CHECK (octet_length(pengguna_ct)>=29 AND substring(pengguna_ct FROM 1 FOR 1)='\x01'::bytea),
    agama_ct bytea CHECK (octet_length(agama_ct)>=29 AND substring(agama_ct FROM 1 FOR 1)='\x01'::bytea),
    no_ktp_bidx bytea CHECK (octet_length(no_ktp_bidx)=32),
    email_bidx bytea CHECK (octet_length(email_bidx)=32),
    pengguna_bidx bytea CHECK (octet_length(pengguna_bidx)=32),
    jenis_kelamin char(1),
    pekerjaan_terakhir varchar(50),
    nama_kppn varchar(50),
    nama_bank varchar(50),
    age_band varchar(10),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS anggota_protected_no_ktp_bidx_idx ON public.anggota_protected(no_ktp_bidx);
CREATE INDEX IF NOT EXISTS anggota_protected_email_bidx_idx ON public.anggota_protected(email_bidx);
CREATE INDEX IF NOT EXISTS anggota_protected_pengguna_bidx_idx ON public.anggota_protected(pengguna_bidx);

CREATE TABLE IF NOT EXISTS public.access_scope (
    scope_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    principal uuid NOT NULL REFERENCES public.app_users(user_id) ON DELETE CASCADE,
    anggota_id uuid REFERENCES public.anggota_protected(anggota_id) ON DELETE CASCADE,
    permission varchar(16) NOT NULL CHECK (permission IN ('read','update','insert')),
    source_label varchar(16) NOT NULL DEFAULT 'manual' CHECK (source_label IN ('synthetic','manual','application')),
    CHECK (anggota_id IS NOT NULL OR permission='insert'),
    UNIQUE NULLS NOT DISTINCT (principal,anggota_id,permission)
);

CREATE TABLE IF NOT EXISTS public.audit_log (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    actor uuid,
    actor_role varchar(32) NOT NULL DEFAULT 'database',
    database_user name NOT NULL DEFAULT session_user,
    effective_role name NOT NULL DEFAULT current_user,
    action varchar(64) NOT NULL CHECK (action ~ '^[a-z][a-z0-9_.:-]{0,63}$'),
    anggota_id uuid,
    field_class varchar(16) NOT NULL CHECK (field_class IN ('PII','FIN','REF','AUTH','SCOPE','ROW')),
    decision varchar(16) NOT NULL CHECK (decision IN ('allowed','denied','error')),
    request_id uuid
);

CREATE OR REPLACE FUNCTION public.request_principal() RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
    RETURN nullif(current_setting('app.principal',true),'')::uuid;
EXCEPTION WHEN invalid_text_representation THEN
    RETURN NULL; -- Missing/invalid auth context denies rows; never substitutes data.
END;
$$;

CREATE OR REPLACE FUNCTION public.touch_updated_at() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN NEW.updated_at := clock_timestamp(); RETURN NEW; END;
$$;
DROP TRIGGER IF EXISTS anggota_touch ON public.anggota_protected;
CREATE TRIGGER anggota_touch BEFORE UPDATE ON public.anggota_protected FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
DROP TRIGGER IF EXISTS app_users_touch ON public.app_users;
CREATE TRIGGER app_users_touch BEFORE UPDATE ON public.app_users FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

CREATE OR REPLACE FUNCTION public.audit_context() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    NEW.actor := public.request_principal();
    SELECT coalesce(u.role,'database') INTO NEW.actor_role FROM (VALUES(1)) AS one(n)
        LEFT JOIN public.app_users AS u ON u.user_id=NEW.actor;
    NEW.database_user := session_user;
    NEW.effective_role := coalesce(nullif(current_setting('role',true),'none'),session_user);
    NEW.occurred_at := clock_timestamp();
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS audit_context ON public.audit_log;
CREATE TRIGGER audit_context BEFORE INSERT ON public.audit_log FOR EACH ROW EXECUTE FUNCTION public.audit_context();

CREATE OR REPLACE FUNCTION public.audit_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE record_id uuid; class_name text;
BEGIN
    IF TG_TABLE_NAME='anggota_protected' THEN
        IF TG_OP='DELETE' THEN record_id:=OLD.anggota_id; ELSE record_id:=NEW.anggota_id; END IF;
        class_name:='ROW';
    ELSIF TG_TABLE_NAME='access_scope' THEN
        IF TG_OP='DELETE' THEN record_id:=OLD.anggota_id; ELSE record_id:=NEW.anggota_id; END IF;
        class_name:='SCOPE';
    ELSE class_name:='AUTH'; END IF;
    INSERT INTO public.audit_log(action,anggota_id,field_class,decision)
      VALUES(TG_TABLE_NAME||'.'||lower(TG_OP),record_id,class_name,'allowed');
    RETURN NULL;
END;
$$;
DROP TRIGGER IF EXISTS anggota_audit ON public.anggota_protected;
CREATE TRIGGER anggota_audit AFTER INSERT OR UPDATE OR DELETE ON public.anggota_protected FOR EACH ROW EXECUTE FUNCTION public.audit_change();
DROP TRIGGER IF EXISTS app_users_audit ON public.app_users;
CREATE TRIGGER app_users_audit AFTER INSERT OR UPDATE OR DELETE ON public.app_users FOR EACH ROW EXECUTE FUNCTION public.audit_change();
DROP TRIGGER IF EXISTS scope_audit ON public.access_scope;
CREATE TRIGGER scope_audit AFTER INSERT OR UPDATE OR DELETE ON public.access_scope FOR EACH ROW EXECUTE FUNCTION public.audit_change();

CREATE OR REPLACE FUNCTION public.scope_new_member() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE principal_id uuid := public.request_principal();
BEGIN
    -- Only a principal pre-authorized by the trusted scope administrator gets a
    -- creator scope, and only for the freshly inserted UUID. No arbitrary grant API.
    IF EXISTS(SELECT 1 FROM public.access_scope AS s JOIN public.app_users AS u ON u.user_id=s.principal
        WHERE s.principal=principal_id AND u.active AND s.permission='insert'
        AND (s.anggota_id IS NULL OR s.anggota_id=NEW.anggota_id)) THEN
        INSERT INTO public.access_scope(principal,anggota_id,permission,source_label)
            VALUES(principal_id,NEW.anggota_id,'read','application'),(principal_id,NEW.anggota_id,'update','application')
            ON CONFLICT DO NOTHING;
    END IF;
    RETURN NULL;
END;
$$;
DROP TRIGGER IF EXISTS member_creator_scope ON public.anggota_protected;
CREATE TRIGGER member_creator_scope AFTER INSERT ON public.anggota_protected FOR EACH ROW EXECUTE FUNCTION public.scope_new_member();

ALTER TABLE public.anggota_protected ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.anggota_protected FORCE ROW LEVEL SECURITY;
ALTER TABLE public.access_scope ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.access_scope FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS member_owner_read ON public.anggota_protected;
CREATE POLICY member_owner_read ON public.anggota_protected FOR SELECT TO schema_owner USING (true);
DROP POLICY IF EXISTS member_app_read ON public.anggota_protected;
CREATE POLICY member_app_read ON public.anggota_protected FOR SELECT TO app_user USING (
    EXISTS(SELECT 1 FROM public.access_scope AS s JOIN public.app_users AS u ON u.user_id=s.principal
        WHERE s.principal=(SELECT public.request_principal()) AND u.active AND s.anggota_id=anggota_protected.anggota_id
        AND s.permission IN ('read','update')));
DROP POLICY IF EXISTS member_app_insert ON public.anggota_protected;
CREATE POLICY member_app_insert ON public.anggota_protected FOR INSERT TO app_user WITH CHECK (
    EXISTS(SELECT 1 FROM public.access_scope AS s JOIN public.app_users AS u ON u.user_id=s.principal
        WHERE s.principal=(SELECT public.request_principal()) AND u.active AND s.permission='insert'
        AND (s.anggota_id IS NULL OR s.anggota_id=anggota_protected.anggota_id)));
DROP POLICY IF EXISTS member_app_update ON public.anggota_protected;
CREATE POLICY member_app_update ON public.anggota_protected FOR UPDATE TO app_user USING (
    EXISTS(SELECT 1 FROM public.access_scope AS s JOIN public.app_users AS u ON u.user_id=s.principal
        WHERE s.principal=(SELECT public.request_principal()) AND u.active AND s.anggota_id=anggota_protected.anggota_id AND s.permission='update'))
    WITH CHECK (EXISTS(SELECT 1 FROM public.access_scope AS s JOIN public.app_users AS u ON u.user_id=s.principal
        WHERE s.principal=(SELECT public.request_principal()) AND u.active AND s.anggota_id=anggota_protected.anggota_id AND s.permission='update'));
DROP POLICY IF EXISTS member_migration ON public.anggota_protected;
CREATE POLICY member_migration ON public.anggota_protected FOR ALL TO migration_user USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS member_backup_read ON public.anggota_protected;
CREATE POLICY member_backup_read ON public.anggota_protected FOR SELECT TO backup_user USING (true);
DROP POLICY IF EXISTS member_scanner_read ON public.anggota_protected;
CREATE POLICY member_scanner_read ON public.anggota_protected FOR SELECT TO scanner_user USING (true);

DROP POLICY IF EXISTS scope_owner ON public.access_scope;
CREATE POLICY scope_owner ON public.access_scope TO schema_owner USING(true) WITH CHECK(true);
DROP POLICY IF EXISTS scope_admin ON public.access_scope;
CREATE POLICY scope_admin ON public.access_scope TO admin_user USING(true) WITH CHECK(true);
DROP POLICY IF EXISTS scope_app_read ON public.access_scope;
CREATE POLICY scope_app_read ON public.access_scope FOR SELECT TO app_user USING(principal=(SELECT public.request_principal()));
DROP POLICY IF EXISTS scope_backup_read ON public.access_scope;
CREATE POLICY scope_backup_read ON public.access_scope FOR SELECT TO backup_user USING(true);

CREATE OR REPLACE VIEW public.analyst_view WITH (security_barrier=true) AS
    SELECT jenis_kelamin,pekerjaan_terakhir,nama_kppn,nama_bank,age_band FROM public.anggota_protected;
-- This is an internal projection, not an analyst interface. The suppressed
-- aggregate view/function are created by 03_analyst_suppression.sql before grants.

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
RESET ROLE;
