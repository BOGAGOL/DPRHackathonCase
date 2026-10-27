-- Applied explicitly by the bootstrap operator for Stage 6; no new table/role.
-- admin_user receives only wrapped-key maintenance functions, never table SELECT.
SET LOCAL ROLE schema_owner;

DROP POLICY IF EXISTS member_owner_rotation_update ON public.anggota_protected;
CREATE POLICY member_owner_rotation_update ON public.anggota_protected
    FOR UPDATE TO schema_owner USING (true) WITH CHECK (true);

-- Explicit extraction avoids relying on ciphertext ordering (v10 vs v2).
CREATE OR REPLACE FUNCTION public.pii_rotation_status()
RETURNS TABLE(key_version integer, rows bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT substring(split_part(dek_pii_wrapped,':',2) from 2)::integer, count(*)
      FROM public.anggota_protected GROUP BY 1 ORDER BY 1;
$$;

CREATE OR REPLACE FUNCTION public.pii_rotation_page(p_after bigint, p_limit integer, p_version integer)
RETURNS TABLE(legacy_row_id bigint, anggota_id uuid, wrapped text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    IF p_limit IS NULL OR p_limit<1 OR p_limit>100 OR p_version IS NULL OR p_version<1 THEN
        RAISE EXCEPTION 'Invalid rotation page bounds';
    END IF;
    RETURN QUERY SELECT a.legacy_row_id,a.anggota_id,a.dek_pii_wrapped
      FROM public.anggota_protected a
      WHERE (p_after IS NULL OR a.legacy_row_id>p_after)
        AND substring(split_part(a.dek_pii_wrapped,':',2) from 2)::integer < p_version
      ORDER BY a.legacy_row_id LIMIT p_limit;
END;
$$;

CREATE OR REPLACE FUNCTION public.pii_rotation_apply(p_changes jsonb, p_version integer)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE item jsonb; old_value text; new_value text; changed integer:=0; affected integer;
BEGIN
    IF p_version IS NULL OR p_version<1 OR p_changes IS NULL OR jsonb_typeof(p_changes)<>'array' THEN
        RAISE EXCEPTION 'Invalid rotation batch';
    END IF;
    IF jsonb_array_length(p_changes)<1 OR jsonb_array_length(p_changes)>100 THEN
        RAISE EXCEPTION 'Invalid rotation batch size';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(p_changes) LOOP
        IF jsonb_typeof(item)<>'object' OR NOT item ?& ARRAY['anggota_id','old_wrapped','new_wrapped']
          OR (SELECT count(*) FROM jsonb_object_keys(item))<>3 THEN
            RAISE EXCEPTION 'Invalid rotation item';
        END IF;
        old_value:=item->>'old_wrapped'; new_value:=item->>'new_wrapped';
        IF old_value IS NULL OR new_value IS NULL OR item->>'anggota_id' IS NULL
          OR old_value !~ '^vault:v[1-9][0-9]*:[A-Za-z0-9+/]+={0,2}$'
          OR new_value !~ '^vault:v[1-9][0-9]*:[A-Za-z0-9+/]+={0,2}$' THEN
            RAISE EXCEPTION 'Invalid wrapped DEK';
        END IF;
        IF octet_length(decode(split_part(old_value,':',3),'base64'))<>60
          OR octet_length(decode(split_part(new_value,':',3),'base64'))<>60
          OR substring(split_part(old_value,':',2) from 2)::integer>=p_version
          OR substring(split_part(new_value,':',2) from 2)::integer<>p_version THEN
            RAISE EXCEPTION 'Invalid wrapped DEK version';
        END IF;
        UPDATE public.anggota_protected SET dek_pii_wrapped=new_value
          WHERE anggota_id=(item->>'anggota_id')::uuid AND dek_pii_wrapped=old_value;
        GET DIAGNOSTICS affected=ROW_COUNT;
        IF affected<>1 THEN RAISE EXCEPTION 'Concurrent wrapped DEK change'; END IF;
        changed:=changed+1;
    END LOOP;
    RETURN changed;
END;
$$;

REVOKE ALL ON FUNCTION public.pii_rotation_status(),public.pii_rotation_page(bigint,integer,integer),
    public.pii_rotation_apply(jsonb,integer) FROM PUBLIC,app_user,analyst_user,auditor_user,
    backup_user,admin_user,migration_user,scanner_user;
GRANT EXECUTE ON FUNCTION public.pii_rotation_status(),public.pii_rotation_page(bigint,integer,integer),
    public.pii_rotation_apply(jsonb,integer) TO admin_user;
RESET ROLE;
