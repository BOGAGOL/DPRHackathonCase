-- F-01: run as trusted database administrator in one transaction, after the
-- approved golden reset. No plaintext, cleanup DELETE, crypto, role or key change.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL row_security = off;
LOCK TABLE public.anggota_protected IN SHARE ROW EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.anggota_protected
               WHERE no_ktp_bidx IS NOT NULL
               GROUP BY no_ktp_bidx HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'Identity uniqueness migration refused: duplicate groups remain';
    END IF;
END;
$$;

-- PostgreSQL's default NULLS DISTINCT preserves unknown/null source identities.
CREATE UNIQUE INDEX IF NOT EXISTS uq_anggota_protected_no_ktp_bidx
    ON public.anggota_protected (no_ktp_bidx);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_index i
        JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=i.indkey[0]
        WHERE i.indexrelid='public.uq_anggota_protected_no_ktp_bidx'::regclass
          AND i.indrelid='public.anggota_protected'::regclass
          AND i.indisunique AND i.indisvalid AND i.indisready AND i.indislive
          AND i.indnkeyatts=1 AND i.indnatts=1 AND i.indpred IS NULL
          AND i.indexprs IS NULL AND NOT i.indnullsnotdistinct
          AND a.attname='no_ktp_bidx'
    ) THEN
        RAISE EXCEPTION 'Identity uniqueness index verification failed';
    END IF;
END;
$$;
