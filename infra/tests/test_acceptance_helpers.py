from pathlib import Path
from types import SimpleNamespace

import pytest

from infra.acceptance.browser import environments
from infra.acceptance.native_lab import laboratory


def test_runtime_does_not_inherit_operator_or_backup_credentials(monkeypatch,tmp_path):
    monkeypatch.setenv("PGPASSWORD","operator-identity-test-sentinel")
    monkeypatch.setenv("OPENBAO_ROOT_TOKEN","root-identity-test-sentinel")
    monkeypatch.setenv("BACKUP_KEY","backup-identity-test-sentinel")
    monkeypatch.setenv("OPENBAO_VALIDATION_TOKEN","scoped-app-test-sentinel")
    settings=SimpleNamespace(database_url="app-url",auth_database_url=None,analyst_database_url="analyst-url",
        auditor_database_url="auditor-url",restored_database="dpr_restore_"+"a"*32,
        openbao_addr="https://127.0.0.1:8200",openbao_cacert="public-ca.crt")
    api,web=environments(settings,tmp_path,8100,3443)
    assert api["DPR_RESTORED_DATABASE"]==settings.restored_database
    assert api["OPENBAO_TOKEN"]=="scoped-app-test-sentinel"
    assert web["NODE_EXTRA_CA_CERTS"].endswith("ca.crt")
    for name in ("PGPASSWORD","OPENBAO_ROOT_TOKEN","BACKUP_KEY","OPENBAO_VALIDATION_TOKEN"):
        assert name not in api and name not in web
    assert "OPENBAO_TOKEN" not in web and "DATABASE_URL" not in web


@pytest.mark.parametrize("pg_version,bao_version",[(b"postgres 17.0",b"OpenBao v2.5.5"),(b"postgres 18.6",b"OpenBao v2.4.0")])
def test_native_lab_rejects_wrong_binary_versions_before_creating_cluster(monkeypatch,tmp_path,pg_version,bao_version):
    monkeypatch.setenv("DPR_NATIVE_PG_BIN",str(tmp_path/"tools"))
    monkeypatch.setenv("DPR_NATIVE_BAO_BIN",str(tmp_path/"bao"))
    monkeypatch.setattr("infra.acceptance.native_lab.subprocess.run",lambda command,**kw:SimpleNamespace(returncode=0,stdout=bao_version if Path(command[0]).name=="bao" else pg_version))
    with pytest.raises(ValueError):
        with laboratory(tmp_path/"fixture"):pytest.fail("Invalid binaries must not create a lab")
    assert not (tmp_path/"fixture").exists()
