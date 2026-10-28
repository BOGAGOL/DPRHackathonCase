"""Durable swap journal. Never drop an original or an unrecognized database."""
import json
import os
from pathlib import Path

import psycopg
from psycopg import sql

from benchmark.common import utc_now, write_json
from benchmark.db_time import monitoring_parameters

NAMES = ('baseline_100k', 'protected_100k')
ALLOWED = set(NAMES) | {n + '__official' for n in NAMES}


class PGStore:
    def __init__(self):
        p = monitoring_parameters()
        if p.get('host') != '127.0.0.1' or str(p.get('port')) != '5433' or p.get('user') != 'postgres':
            raise RuntimeError('swap_requires_explicit_local_admin')
        p.update(dbname='template1', application_name='dpr-api-swap', options='-c default_transaction_read_only=off')
        self.conn = psycopg.connect(**p, autocommit=True)
        if not self.conn.execute("SELECT pg_try_advisory_lock(hashtext('dpr-api-name-swap'))").fetchone()[0]:
            self.conn.close()
            raise RuntimeError('swap_controller_already_running')

    def entries(self):
        return {name: {'oid': oid, 'allow_connections': allow} for name, oid, allow in
                self.conn.execute('SELECT datname,oid,datallowconn FROM pg_database WHERE datname=ANY(%s)', (list(ALLOWED),))}

    def sessions(self, oid):
        return self.conn.execute('SELECT count(*) FROM pg_stat_activity WHERE datid=%s', (oid,)).fetchone()[0]

    def rename(self, old, new):
        if old not in ALLOWED or new not in ALLOWED:
            raise ValueError('unauthorized_database_name')
        self.conn.execute(sql.SQL('ALTER DATABASE {} RENAME TO {}').format(sql.Identifier(old), sql.Identifier(new)))

    def allow(self, name, enabled):
        if name not in ALLOWED:
            raise ValueError('unauthorized_database_name')
        self.conn.execute(sql.SQL('ALTER DATABASE {} ALLOW_CONNECTIONS {}').format(sql.Identifier(name), sql.Literal(bool(enabled))))

    def clone(self, name, template):
        if name not in NAMES or template != name + '__official':
            raise ValueError('unauthorized_clone')
        self.conn.execute(sql.SQL('CREATE DATABASE {} TEMPLATE {}').format(sql.Identifier(name), sql.Identifier(template)))

    def drop_copy(self, name, expected_oid):
        if name not in NAMES or self.entries().get(name, {}).get('oid') != expected_oid:
            raise RuntimeError('copy_oid_mismatch_refuse_drop')
        self.conn.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datid=%s AND pid<>pg_backend_pid()', (expected_oid,))
        self.conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))

    def close(self):
        self.conn.close()


class Swap:
    def __init__(self, store, path):
        self.store, self.path = store, Path(path)
        self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else None

    def save(self, status):
        self.state.update(status=status, updated_at_utc=utc_now())
        write_json(self.path, self.state)
        with self.path.open('r+b') as handle:
            os.fsync(handle.fileno())

    def swap(self):
        if self.state is not None:
            raise RuntimeError('existing_swap_journal_use_recovery_not_overwrite')
        entries = self.store.entries()
        if any(n not in entries or n + '__official' in entries for n in NAMES):
            raise RuntimeError('swap_names_not_pristine')
        if any(self.store.sessions(entries[n]['oid']) for n in NAMES):
            raise RuntimeError('official_database_has_sessions')
        self.state = {'schema_version': 1, 'started_at_utc': utc_now(), 'originals': {n: entries[n] for n in NAMES},
                      'copies': {}, 'events': [], 'app': None, 'verification': None}
        self.save('swapping')
        for name in NAMES:
            self.store.rename(name, name + '__official')
            self.state['events'].append({'action': 'original_renamed', 'database': name, 'at_utc': utc_now()})
            self.save('swapping')
            # Prevent new connections to the archived original. Flags are restored later.
            self.store.allow(name + '__official', False)
            if self.store.sessions(self.state['originals'][name]['oid']):
                raise RuntimeError('template_has_sessions')
            self.store.clone(name, name + '__official')
            oid = self.store.entries()[name]['oid']
            if oid in {v['oid'] for v in self.state['originals'].values()}:
                raise RuntimeError('copy_reuses_original_oid')
            self.state['copies'][name] = oid
            self.save('swapping')
        self.save('swapped')

    def restore(self):
        if self.state is None or self.state['status'] == 'restored':
            return
        try:
            self.save('restoring')
            originals = {v['oid'] for v in self.state['originals'].values()}
            for name in NAMES:
                entries = self.store.entries()
                expected = self.state['originals'][name]['oid']
                original = entries.get(name)
                archived = entries.get(name + '__official')
                if original and original['oid'] == expected and not archived:
                    self.store.allow(name, self.state['originals'][name]['allow_connections'])
                    continue
                if not archived or archived['oid'] != expected:
                    raise RuntimeError('original_oid_not_found_refuse_recovery')
                if original:
                    copy_oid = self.state['copies'].get(name)
                    if not copy_oid or original['oid'] != copy_oid or copy_oid in originals:
                        raise RuntimeError('unknown_database_refuse_drop')
                    self.store.drop_copy(name, copy_oid)
                if self.store.sessions(expected):
                    raise RuntimeError('archived_original_has_sessions')
                self.store.allow(name + '__official', self.state['originals'][name]['allow_connections'])
                self.store.rename(name + '__official', name)
                self.state['events'].append({'action': 'original_name_restored', 'database': name, 'at_utc': utc_now()})
                self.save('restoring')
            self.save('names_restored_pending_verification')
        except Exception as error:
            self.state['recovery_error_type'] = type(error).__name__
            self.save('restore_failed')
            raise RuntimeError('database_name_recovery_failed_check_journal') from None
