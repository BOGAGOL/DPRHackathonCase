"""Native PG18 invariants in an explicitly marked, disposable local test cluster."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
import os
import secrets
from threading import Barrier
from uuid import uuid4

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
import psycopg
from psycopg import sql
import pytest
from sqlalchemy import create_engine, delete, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from conftest import FakeCrypto, Lab, csrf, invented_row, login
from service_app.config import Settings
from service_app.main import create_app
from service_app.models import AuditLog, Base, User, protected_members
from service_app.protected_control import ProtectedBase, ProtectedUser, scopes, audit_table
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from f01_identity import apply_identity_unique, identity_state

pytestmark = pytest.mark.integration
MIGRATION = Path(__file__).resolve().parents[2] / 'sql/protected/04_identity_unique.sql'


@pytest.fixture(params=['plain', 'protected'])
def native_lab(request):
    configured = os.environ.get('DPR_F01_TEST_DATABASE_URL')
    if not configured:
        pytest.skip('Set DPR_F01_TEST_DATABASE_URL for a marked disposable PG18 cluster')
    url = make_url(configured)
    assert url.host == '127.0.0.1' and url.database == 'dpr_f01_tests' and url.username == 'postgres'
    params = dict(host=url.host, port=url.port, dbname=url.database, user=url.username)
    name = 'dpr_f01_' + uuid4().hex
    with psycopg.connect(**params, autocommit=True) as admin:
        assert admin.execute("SELECT current_setting('dpr.test_cluster',true)").fetchone()[0] == 'f01'
        assert int(admin.execute('SHOW server_version_num').fetchone()[0]) >= 180000
        if not admin.execute("SELECT 1 FROM pg_roles WHERE rolname='app_user'").fetchone():
            admin.execute('CREATE ROLE app_user LOGIN NOSUPERUSER NOBYPASSRLS')
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    engine = create_engine(url.set(database=name))
    application = None
    try:
        Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name != 'audit_log'])
        ProtectedBase.metadata.create_all(engine, tables=[t for t in ProtectedBase.metadata.sorted_tables if t.name != 'audit_log'])
        (AuditLog.__table__ if request.param == 'plain' else audit_table).create(engine)
        password, user_id = secrets.token_urlsafe(24), str(uuid4())
        encoded = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(password)
        with Session(engine) as db:
            db.add(User(id=user_id, username='test-privileged_officer', password_hash=encoded,
                        role='privileged_officer', principal='fixture', active=True))
            db.add(ProtectedUser(id=user_id, username='test-privileged_officer', password_hash=encoded,
                                 role='privileged_officer', active=True))
            db.flush()
            db.execute(scopes.insert().values(principal=user_id, anggota_id=None, permission='insert'))
            db.commit()
        runtime = url.set(database=name, username='app_user')
        crypto = FakeCrypto()
        application = create_app(Settings(mode=request.param, database_url=runtime.render_as_string(hide_password=False), testing=True), crypto=crypto)
        fixture = Lab(application, None, engine, password, {'privileged_officer': user_id}, [], crypto, request.param)
        fixture.rows.extend(fixture.add_member(i) for i in [1, 2, 3])
        with engine.begin() as db:
            db.execute(text("SELECT setval(pg_get_serial_sequence('anggota','id'),4,false)"))
            db.execute(text('CREATE SEQUENCE service_legacy_id_seq START 4'))
            db.execute(text('''CREATE FUNCTION public.f01_creator_scope() RETURNS trigger
              LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN
              INSERT INTO public.access_scope(principal,anggota_id,permission)
              SELECT principal,NEW.anggota_id,p FROM public.access_scope
              CROSS JOIN (VALUES ('read'),('update')) AS permissions(p)
              WHERE permission='insert' AND anggota_id IS NULL
              AND principal=nullif(current_setting('app.principal',true),'')::uuid;
              RETURN NULL; END; $$'''))
            db.execute(text('CREATE TRIGGER f01_creator_scope AFTER INSERT ON anggota_protected FOR EACH ROW EXECUTE FUNCTION public.f01_creator_scope()'))
            db.execute(text('ALTER TABLE anggota_protected ENABLE ROW LEVEL SECURITY'))
            db.execute(text('ALTER TABLE anggota_protected FORCE ROW LEVEL SECURITY'))
            db.execute(text('''CREATE POLICY fixture_read ON anggota_protected FOR SELECT TO app_user
               USING (EXISTS (SELECT 1 FROM public.access_scope s WHERE s.anggota_id=anggota_protected.anggota_id
               AND s.principal=nullif(current_setting('app.principal',true),'')::uuid AND s.permission IN ('read','update')))'''))
            db.execute(text('''CREATE POLICY fixture_insert ON anggota_protected FOR INSERT TO app_user
               WITH CHECK (EXISTS (SELECT 1 FROM public.access_scope s WHERE s.anggota_id IS NULL
               AND s.principal=nullif(current_setting('app.principal',true),'')::uuid AND s.permission='insert'))'''))
            db.execute(text('GRANT USAGE ON SCHEMA public TO app_user'))
            db.execute(text('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO app_user'))
            db.execute(text('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user'))
            db.execute(text('DROP INDEX uq_anggota_protected_no_ktp_bidx'))
            db.connection.driver_connection.execute(MIGRATION.read_text(), prepare=False)
        yield fixture
    finally:
        if application:
            for owned in {application.state.engine, application.state.auth_engine}:
                owned.dispose()
        engine.dispose()
        with psycopg.connect(**params, autocommit=True) as admin:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def test_native_parallel_requests_commit_one_identity(native_lab):
    lab = native_lab
    barrier = Barrier(2)
    payload = invented_row(44)
    with ExitStack() as stack:
        clients = [stack.enter_context(TestClient(lab.app, base_url='https://localhost:3443', raise_server_exceptions=False)) for _ in range(2)]
        for client in clients:
            lab.client = client
            login(lab, 'privileged_officer')
        def synchronize_insert(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith('INSERT INTO anggota_protected'):
                barrier.wait(timeout=15)
        def write(client):
            if lab.mode == 'plain':
                barrier.wait(timeout=15)
            return client.post('/anggota', headers=csrf(client), json=payload)
        if lab.mode == 'protected':
            event.listen(lab.app.state.engine, 'before_cursor_execute', synchronize_insert)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(write, clients))
        finally:
            if lab.mode == 'protected':
                event.remove(lab.app.state.engine, 'before_cursor_execute', synchronize_insert)
        assert sorted(response.status_code for response in responses) == [201, 409]
        conflict = next(r for r in responses if r.status_code == 409)
        assert conflict.json() == {'detail': 'Data tidak dapat dibuat karena konflik identitas'}
        result = clients[0].get('/anggota/search', params={'no_ktp': payload['no_ktp']})
        assert result.status_code == 200 and result.json()['total'] == 1 and len(result.json()['items']) == 1


def test_native_hidden_identity_is_unique_across_rls(native_lab):
    if native_lab.mode == 'plain':
        pytest.skip('Plain baseline has no protected RLS')
    lab = native_lab
    with lab.engine.begin() as db:
        record = db.scalar(select(protected_members.c.anggota_id).where(protected_members.c.legacy_row_id == 1))
        db.execute(delete(scopes).where(scopes.c.anggota_id == record))
    with TestClient(lab.app, base_url='https://localhost:3443', raise_server_exceptions=False) as client:
        lab.client = client
        login(lab, 'privileged_officer')
        assert client.get('/anggota/1').status_code == 404
        response = client.post('/anggota', headers=csrf(client), json={**invented_row(44), 'no_ktp': lab.rows[0]['no_ktp']})
        assert response.status_code == 409 and 'anggota_id' not in response.text


def test_native_migration_rejects_duplicates_atomically(native_lab):
    with native_lab.engine.begin() as db:
        db.execute(text('DROP INDEX uq_anggota_protected_no_ktp_bidx'))
        db.execute(text('UPDATE anggota_protected SET no_ktp_bidx=(SELECT no_ktp_bidx FROM anggota_protected WHERE legacy_row_id=1) WHERE legacy_row_id=2'))
    with pytest.raises(psycopg.Error) as caught, native_lab.engine.begin() as db:
        db.connection.driver_connection.execute(MIGRATION.read_text(), prepare=False)
    assert 'duplicate groups remain' in str(caught.value)
    with native_lab.engine.connect() as db:
        assert db.scalar(text("SELECT to_regclass('public.uq_anggota_protected_no_ktp_bidx')")) is None
        assert db.scalar(text('SELECT count(*) FROM anggota_protected')) == 3


def test_native_migration_rejects_wrong_existing_index(native_lab):
    with native_lab.engine.begin() as db:
        db.execute(text('DROP INDEX uq_anggota_protected_no_ktp_bidx'))
        db.execute(text('CREATE INDEX uq_anggota_protected_no_ktp_bidx ON anggota_protected(no_ktp_bidx)'))
    with pytest.raises(psycopg.Error) as caught, native_lab.engine.begin() as db:
        db.connection.driver_connection.execute(MIGRATION.read_text(), prepare=False)
    assert 'index verification failed' in str(caught.value)


def test_native_migration_idempotent_and_null_identities_preserved(native_lab):
    with native_lab.engine.begin() as db:
        db.execute(text('UPDATE anggota_protected SET no_ktp_bidx=NULL,no_ktp_ct=NULL WHERE legacy_row_id IN (1,2)'))
        db.connection.driver_connection.execute(MIGRATION.read_text(), prepare=False)
        db.connection.driver_connection.execute(MIGRATION.read_text(), prepare=False)
        assert db.scalar(text('SELECT count(*) FROM anggota_protected WHERE no_ktp_bidx IS NULL')) == 2
        state = identity_state(db.connection.driver_connection)
        assert state == {'members': 3, 'pentest_duplicate_ids_remaining': 0,
                         'duplicate_identity_groups': 0, 'unique_index_valid': True}
        assert apply_identity_unique(db.connection.driver_connection) == state
