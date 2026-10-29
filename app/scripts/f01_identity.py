"""Trusted F-01 migration/metadata CLI; no member values in evidence or errors."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'app/backend'), str(ROOT / 'app/scripts')]

import psycopg
from service_app.config import Settings
from pentest_prepare import setup_url


def identity_state(connection):
    counts = connection.execute('''SELECT count(*),
        count(*) FILTER (WHERE legacy_row_id IN (735,737))
        FROM public.anggota_protected''').fetchone()
    groups = connection.execute('''SELECT count(*) FROM (
        SELECT 1 FROM public.anggota_protected WHERE no_ktp_bidx IS NOT NULL
        GROUP BY no_ktp_bidx HAVING count(*)>1) AS duplicate_groups''').fetchone()[0]
    index = connection.execute('''SELECT EXISTS (
        SELECT 1 FROM pg_index i JOIN pg_attribute a
        ON a.attrelid=i.indrelid AND a.attnum=i.indkey[0]
        WHERE i.indexrelid=to_regclass('public.uq_anggota_protected_no_ktp_bidx')
        AND i.indrelid='public.anggota_protected'::regclass
        AND i.indisunique AND i.indisvalid AND i.indisready AND i.indislive
        AND i.indnkeyatts=1 AND i.indnatts=1 AND i.indpred IS NULL
        AND i.indexprs IS NULL AND NOT i.indnullsnotdistinct AND a.attname='no_ktp_bidx')''').fetchone()[0]
    return {'members': counts[0], 'pentest_duplicate_ids_remaining': counts[1],
            'duplicate_identity_groups': groups, 'unique_index_valid': bool(index)}


def apply_identity_unique(connection):
    connection.execute((ROOT / 'sql/protected/04_identity_unique.sql').read_text(encoding='utf-8'), prepare=False)
    state = identity_state(connection)
    if not state['unique_index_valid'] or state['duplicate_identity_groups']:
        raise ValueError('Identity invariant verification failed')
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inspect', 'apply', 'verify'])
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args(argv)
    report = {'schema_version': 1, 'finding': 'F-01', 'passed': False, 'command': args.command,
              'time_wib': datetime.now(timezone(timedelta(hours=7))).isoformat(),
              'member_values_written_to_evidence': False}
    try:
        settings = Settings.from_env()
        url = setup_url(settings, os.environ['APP_SETUP_DATABASE_URL'])
        if settings.mode != 'protected' or url.database != 'protected_734':
            raise ValueError('Only the approved protected_734 deployment is allowed')
        with psycopg.connect(url.set(drivername='postgresql').render_as_string(hide_password=False),
                options='-c log_statement=none -c log_min_error_statement=panic -c log_parameter_max_length_on_error=0') as connection:
            if args.command != 'apply':
                connection.execute('SET TRANSACTION READ ONLY')
            connection.execute('SET LOCAL row_security=off')
            report['before'] = identity_state(connection)
            if args.command == 'apply':
                if report['before']['members'] != 734 or report['before']['pentest_duplicate_ids_remaining']:
                    raise ValueError('Run the approved golden reset first')
                report['after'] = apply_identity_unique(connection)
            else:
                report['after'] = report['before']
            state = report['after']
            if args.command != 'inspect' and (state['members'] != 734 or state['pentest_duplicate_ids_remaining']
                    or state['duplicate_identity_groups'] or not state['unique_index_valid']):
                raise ValueError('Identity invariant verification failed')
        report['passed'] = True
    except Exception:
        report['error'] = 'f01_operation_failed_details_withheld'
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'command': args.command, 'report': str(args.evidence)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
