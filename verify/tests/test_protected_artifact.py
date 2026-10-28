import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import yaml

from datagen.model import COLUMNS
from dprcrypto import encrypt, index_message
from verify import protected_artifact as artifact
from verify.tests.test_leakage import rows, ledger


@pytest.fixture
def protected_fixture(rows):
    profile=yaml.safe_load(Path('policy/protection_profile.yaml').read_text(encoding='utf-8'))
    pii,fin,search=os.urandom(32),os.urandom(32),os.urandom(32)
    wrapped='vault:v1:'+base64.b64encode(os.urandom(60)).decode()
    records=[]
    for source in rows:
        identity=str(uuid4())
        row={'anggota_id':identity,'legacy_row_id':source['id'],'protection_version':1,
             'dek_pii_wrapped':wrapped,'dek_fin_wrapped':wrapped,'age_band':artifact.age_band(source['tanggal_lahir'])}
        for c,cfg in profile['columns'].items():
            value=None if source[c] is None else str(source[c])
            row[cfg['storage_column']]=encrypt(value,pii if cfg['domain']=='PII' else fin,column=c,anggota_id=identity) if cfg['aead'] else value
            if cfg['bidx']:
                row[cfg['bidx_column']]=hmac.digest(search,index_message(c,value),'sha256')
        records.append(row)
    client=MagicMock()
    client.unwrap.side_effect=lambda kek,wrapped:[pii if kek=='pii-kek' else fin]*len(wrapped)
    client.hmac.side_effect=lambda col,values:[None if v is None else hmac.digest(search,index_message(col,v),'sha256') for v in values]
    client.denied.return_value=True
    return profile,records,client


def test_all_scenarios_actual_aead_and_dictionary(ledger,protected_fixture):
    profile,records,client=protected_fixture
    for scenario in artifact.SCENARIOS:
        populations,residual,equality,denied=artifact.measure(iter(records),ledger,profile,scenario,None if scenario.endswith('no_key') else client)
        assert populations['all']['rows']==3 and len(equality)==8
        assert residual['populations']['source_734']['birth_reference_status'].startswith('NOT_AVAILABLE')
        exposed=populations['all']['exposed_cells']
        expected=set(artifact.PII) if scenario.endswith('pii_key') else set(artifact.FIN) if scenario.endswith('finance_key') else set(artifact.SEARCH) if scenario.endswith('search_key') else set()
        assert set(exposed)==expected
    client.denied.return_value=False
    with pytest.raises(ValueError,match='excessive'): artifact.measure(iter(records),ledger,profile,'protected_dump_with_pii_key',client)
    with pytest.raises(ValueError,match='Duplicate'): artifact.measure(iter(records+[records[0]]),ledger,profile,'protected_dump_no_key')
    with pytest.raises(ValueError,match='Incomplete'): artifact.measure(iter(records[:1]),ledger,profile,'protected_dump_no_key')
    expected=ledger.lookup([1,2,735]); records[0]['nama_ct']=records[1]['nama_ct']
    with pytest.raises(Exception,match='authentication failed'):
        artifact.evaluate_batch(records,expected,profile,'protected_dump_with_pii_key',client)


def test_copy_parser_and_truncation(tmp_path,protected_fixture):
    profile,records,_=protected_fixture
    path=tmp_path/'artifact.sql'
    columns=list(records[0])
    lines=['COPY public.other_table (dummy) FROM stdin;\nignored\n\\.\n',
           'COPY public.anggota_protected ('+', '.join(columns)+') FROM stdin;\n']
    for row in records:
        values=[]
        for c in columns:
            value=row[c]
            values.append(r'\N' if value is None else r'\\x'+value.hex() if isinstance(value,bytes) else str(value))
        lines.append('\t'.join(values)+'\n')
    lines.append('\\.\n')
    path.write_text(''.join(lines),encoding='utf-8')
    assert list(artifact.protected_rows(path,profile))==records
    path.write_text(''.join(lines[:-1]),encoding='utf-8')
    with pytest.raises(ValueError): list(artifact.protected_rows(path,profile))
    path.write_text('COPY public.anggota_protected (legacy_row_id) FROM stdin;\n')
    with pytest.raises(ValueError): list(artifact.protected_rows(path,profile))


def test_restricted_transit_identity_errors_and_batches(monkeypatch,protected_fixture):
    profile,records,_=protected_fixture
    conn=MagicMock()
    response=MagicMock(status_code=200)
    response.json.return_value={'data':{'policies':['modc-leak-pii'],'ttl':100,'explicit_max_ttl':14400}}
    conn.request.return_value=response
    monkeypatch.setattr(artifact.httpx,'Client',lambda **kw:conn)
    monkeypatch.setattr(artifact.ssl,'create_default_context',lambda **kw:SimpleNamespace(minimum_version=None))
    monkeypatch.setenv('DPR_LEAK_TOKEN',os.urandom(32).hex())
    monkeypatch.setenv('OPENBAO_ADDR','https://127.0.0.1:8200')
    monkeypatch.setenv('OPENBAO_CACERT','synthetic-ca-path')
    client=artifact.AttackerTransit('protected_dump_with_pii_key')
    dek=os.urandom(32)
    response.json.return_value={'data':{'batch_results':[{'reference':'0','plaintext':base64.b64encode(dek).decode()}]}}
    assert client.unwrap('pii-kek',[records[0]['dek_pii_wrapped']])==[dek]
    response.json.return_value={'data':{'batch_results':[{'reference':'0','hmac':'vault:v1:'+base64.b64encode(os.urandom(32)).decode()}]}}
    assert len(client.hmac('email',['fixture@example.test'])[0])==32
    assert client.hmac('email',[None])==[None]
    response.status_code=403
    assert client.denied('finance-kek',records[0]['dek_fin_wrapped'])
    response.status_code=500
    with pytest.raises(ValueError): client.request('test')
    client.close(); assert client.token==''
    response.status_code=200
    response.json.return_value={'data':{'policies':['svc-app'],'ttl':100,'explicit_max_ttl':14400}}
    with pytest.raises(ValueError): artifact.AttackerTransit('protected_dump_with_pii_key')
    monkeypatch.setenv('OPENBAO_ADDR','http://127.0.0.1:8200')
    with pytest.raises(ValueError): artifact.AttackerTransit('protected_dump_with_pii_key')


def test_run_and_cli_machine_outputs(monkeypatch,tmp_path,ledger,protected_fixture):
    profile,records,client=protected_fixture
    private=tmp_path/'private'
    dump=private/'fixture.dump'; dump.write_bytes(b'PGDMPfixture')
    known=Path(ledger.connection.execute('PRAGMA database_list').fetchone()[2])
    (tmp_path/'policy').mkdir()
    (tmp_path/'policy/protection_profile.yaml').write_text(yaml.safe_dump(profile))
    datasets=tmp_path/'evidence/datasets'; datasets.mkdir(parents=True)
    (datasets/'baseline_100k.json').write_text(json.dumps({'baseline_checksum_sha256':ledger.meta['baseline_checksum_sha256']}))
    monkeypatch.setattr(artifact,'ROOT',tmp_path)
    monkeypatch.setattr(artifact,'require_disk_space',lambda:10**11)
    monkeypatch.setattr(artifact,'KnownValues',lambda p:ledger)
    monkeypatch.setattr(ledger,'close',MagicMock())
    monkeypatch.setattr(artifact,'expand_dump',lambda a,b:b.write_text('synthetic fixture'))
    monkeypatch.setattr(artifact,'protected_rows',lambda *a:iter(records))
    result=artifact.run(dump,known,'protected_100k','protected_dump_no_key')
    assert result['populations']['all']['ESCE']['ratio']==0
    assert not result['DBR']['crypto_client_constructed']
    monkeypatch.setattr(artifact,'AttackerTransit',lambda s:client)
    result=artifact.run(dump,known,'protected_100k','protected_dump_with_finance_key')
    assert result['DBR']['domains_decrypted']==['FIN']
    with pytest.raises(ValueError): artifact.run(dump,known,'postgres','protected_dump_no_key')
    monkeypatch.setattr('sys.argv',['verify.protected_artifact','--artifact',str(dump),'--known-values',str(known),'--db','protected_100k','--scenario','protected_dump_no_key'])
    monkeypatch.setattr(artifact,'run',lambda *a:{'dataset':'protected_100k','status':'PASSED','elapsed_s':0.})
    artifact.main()
    monkeypatch.setattr(artifact,'run',MagicMock(side_effect=RuntimeError('do not disclose values')))
    with pytest.raises(SystemExit): artifact.main()
    assert 'do not disclose' not in (tmp_path/'evidence/leak/protected_100k/protected_dump_no_key_failure.json').read_text()
