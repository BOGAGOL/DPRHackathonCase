"""Real key rotation/resume, no-decrypt operator and old-backup compatibility."""

import base64
import json
import os

import psycopg
from psycopg.types.json import Jsonb
import pytest

from dprcrypto import OpenBaoClient, OpenBaoError
from infra.security import REPO
from infra.rotation.runner import LOCK, execute, prepare, status
from infra.rotation.worker import RotationError
from scripts.backup.postgres import drop_created_database
from scripts.backup.runner import backup, restore
from scripts.backup.tests.test_integration import laboratory


def test_real_rotation_resume_full_decryption_and_old_backup(laboratory, monkeypatch):
    lab = laboratory; params = lab["params"]; database = "protected_734"
    writer = {**params, "dbname": database, "user": "admin_user", "password": lab["passwords"]["admin_user"]}
    reader = {**params, "dbname": database, "user": "scanner_user", "password": lab["passwords"]["scanner_user"]}
    token = json.loads(next((lab["root"]/"openbao/tokens").glob("key-operator-*.json")).read_text())["auth"]["client_token"]
    monkeypatch.setenv("OPENBAO_KEY_OPERATOR_TOKEN", token)
    report = {"schema_version": 1, "passed": False, "scope": "17 invented records, TLS PG18/OpenBao 2.5.5, real subprocesses", "checks": {}}
    checks = report["checks"]; restored = None
    try:
        # Missing prepare must not cause a rotation.
        with pytest.raises(psycopg.errors.UndefinedFunction): execute([database], writer, reader)
        assert prepare({**params, "dbname": database})["passed"]
        assert prepare({**params, "dbname": database})["new_tables"] == 0
        with psycopg.connect(**writer, autocommit=True) as coordinator:
            assert status(coordinator) == {"1": 17}
            with pytest.raises(psycopg.errors.InsufficientPrivilege): coordinator.execute("SELECT * FROM public.anggota_protected")
            with pytest.raises(psycopg.errors.InsufficientPrivilege): coordinator.execute("UPDATE public.anggota_protected SET dek_fin_wrapped=dek_fin_wrapped")
            coordinator.execute("SELECT pg_advisory_lock(%s)", (LOCK,))
            with pytest.raises(RotationError, match="rotation_already_running"): execute([database], writer, reader)
        checks["coordinator_only_wrapped_key_functions"] = True
        with psycopg.connect(**{**params, "dbname": database}, autocommit=True) as admin:
            for role in ("app_user", "backup_user", "scanner_user", "analyst_user", "auditor_user"):
                from psycopg import sql
                admin.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
                with pytest.raises(psycopg.errors.InsufficientPrivilege): admin.execute("SELECT * FROM public.pii_rotation_status()")
                admin.execute("RESET ROLE")
        archive = backup(database, lab["backup_params"], lab["keys"], lab["store"], container=lab["container"])
        checkpoints = []
        paused = execute([database], writer, reader, batch_size=5, max_batches=1, checkpoint=lambda state: checkpoints.append(json.loads(json.dumps(state))))
        assert paused["status"] == "paused" and paused["target_version"] == 2
        assert paused["databases"][database]["rewrapped_rows"] == 5
        checks["pause_commits_atomic_batch"] = paused["databases"][database]["after_versions"] == {"1": 12, "2": 5}
        complete = execute([database], writer, reader, batch_size=5, resume_version=2)
        checks["resume_does_not_rotate_again"] = complete["key_version_before"] == complete["key_version_after"] == 2
        checks["all_wrapped_keys_v2"] = complete["databases"][database]["after_versions"] == {"2": 17}
        checks["full_field_decryption_and_unchanged_deks"] = all(complete["databases"][database]["validation"][name] for name in ("passed", "all_record_deks_unchanged", "all_plaintext_values_unchanged", "ciphertext_finance_bidx_ref_unchanged"))
        repeat = execute([database], writer, reader, resume_version=2)
        checks["rewrap_idempotent"] = repeat["databases"][database]["rewrapped_rows"] == 0
        with OpenBaoClient(token_env="OPENBAO_KEY_OPERATOR_TOKEN") as operator:
            with psycopg.connect(**reader) as connection:
                wrapped = connection.execute("SELECT dek_pii_wrapped FROM public.anggota_protected LIMIT 1").fetchone()[0]
            with pytest.raises(OpenBaoError): operator.unwrap("pii-kek", wrapped)
            with pytest.raises(OpenBaoError): operator.wrap("pii-kek", os.urandom(32))
        checks["key_operator_cannot_encrypt_or_decrypt"] = True
        # CAS mismatch must roll back the batch; no column other than wrapped PII
        # can be supplied to the helper, and versions cannot be downgraded.
        with psycopg.connect(**reader) as connection:
            identity, old = connection.execute("SELECT anggota_id,dek_pii_wrapped FROM public.anggota_protected LIMIT 1").fetchone()
        fake = "vault:v3:"+base64.b64encode(os.urandom(60)).decode()
        wrong_old = "vault:v2:"+base64.b64encode(os.urandom(60)).decode()
        valid_shape = {"anggota_id": str(identity), "old_wrapped": old, "new_wrapped": fake}
        with psycopg.connect(**writer, autocommit=True) as coordinator:
            for changes, version in [([], 3), ({}, 3), ([{}], 3), ([valid_shape]*101, 3),
                    ([{**valid_shape, "old_wrapped": wrong_old}], 3), ([{**valid_shape, "extra": "denied"}], 3),
                    ([valid_shape], 2), ([{**valid_shape, "new_wrapped": None}], 3)]:
                with pytest.raises(psycopg.Error): coordinator.execute("SELECT public.pii_rotation_apply(%s,%s)", (Jsonb(changes), version))
            with pytest.raises(psycopg.Error): coordinator.execute("SELECT * FROM public.pii_rotation_page(NULL,101,3)")
            checks["cas_invalid_batch_and_downgrade_refused"] = status(coordinator) == {"2": 17}
        restored = restore(archive["manifest"], params, lab["keys"], container=lab["container"], with_openbao=True)
        checks["pre_rotation_backup_still_decrypts"] = restored["decryption_smoke"]["records"] == 16
        checks["old_key_versions_not_disabled"] = complete["min_decryption_version_before"] == 1 and not complete["minimum_key_versions_changed"]
        report.update(passed=all(checks.values()), rotation=complete)
        assert report["passed"]
    finally:
        if restored: drop_created_database(params, restored["created_database"])
        path = REPO/"evidence/keys/integration.json"; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
