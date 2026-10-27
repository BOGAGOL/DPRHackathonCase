"""Deployment guards and policy/adapter boundaries independent of any live service."""
import importlib
import secrets
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import URL

from service_app.config import Settings
from service_app.crypto import CryptoUnavailable, ToolkitAdapter
from service_app.main import create_app
from service_app.policy import can_access, can_edit, detail_policy, mask, mask_list_name, owns_only
from service_app.repository import normalized


def runtime_url(ca, *, user="app_user", database="baseline_100k", sslmode="verify-full"):
    return URL.create("postgresql+psycopg", username=user, password=secrets.token_urlsafe(24),
                      host="localhost", port=5433, database=database,
                      query={"sslmode": sslmode, "sslrootcert": str(ca)}).render_as_string(hide_password=False)


def test_plain_mode_can_start_without_crypto_or_secret_material():
    app = create_app(Settings(mode="plain", database_url="sqlite://", testing=True))
    assert app.state.protection is None
    app.state.engine.dispose()


@pytest.mark.parametrize("mode", ["plaintext", "legacy", "", "PLAIN"])
def test_unknown_modes_fail_closed(mode):
    with pytest.raises(ValueError):
        Settings(mode=mode, database_url="sqlite://", testing=True).validate()


@pytest.mark.parametrize("database", ["postgres", "dpr_protected", "baseline_734", "protected_100k", "protected_734"])
def test_plain_mode_rejects_source_and_other_database_targets(tmp_path, database):
    ca = tmp_path / "test-root.crt"
    ca.touch()
    with pytest.raises(ValueError):
        Settings(mode="plain", database_url=runtime_url(ca, database=database)).validate()


@pytest.mark.parametrize("identity", ["postgres", "schema_owner", "migration_user", "bench_user", "backup_user"])
def test_runtime_cannot_use_privileged_or_benchmark_identity(tmp_path, identity):
    ca = tmp_path / "test-root.crt"
    ca.touch()
    with pytest.raises(ValueError):
        Settings(mode="plain", database_url=runtime_url(ca, user=identity)).validate()


@pytest.mark.parametrize("sslmode", ["disable", "allow", "prefer", "require", "verify-ca"])
def test_runtime_requires_verify_full_postgres_tls(tmp_path, sslmode):
    ca = tmp_path / "test-root.crt"
    ca.touch()
    with pytest.raises(ValueError):
        Settings(mode="plain", database_url=runtime_url(ca, sslmode=sslmode)).validate()


def test_role_specific_database_identities_and_ca_required(tmp_path):
    ca = tmp_path / "test-root.crt"
    ca.touch()
    settings = Settings(mode="plain", database_url=runtime_url(ca),
                        analyst_database_url=runtime_url(ca, user="analyst_user"),
                        auditor_database_url=runtime_url(ca, user="auditor_user"))
    assert settings.validate() is settings
    with pytest.raises(ValueError):
        Settings(mode="plain", database_url=runtime_url(ca), analyst_database_url=runtime_url(ca)).validate()
    ca.unlink()
    with pytest.raises(ValueError):
        settings.validate()


@pytest.mark.parametrize("auth_database", ["postgres", "protected_100k", "protected_734"])
def test_auth_database_must_match_the_selected_mode(tmp_path, auth_database):
    ca = tmp_path / "test-root.crt"
    ca.touch()
    with pytest.raises(ValueError):
        Settings(mode="plain", database_url=runtime_url(ca), auth_database_url=runtime_url(ca, database=auth_database)).validate()


def test_origin_and_short_session_guards():
    with pytest.raises(ValueError):
        Settings(mode="plain", database_url="sqlite://", testing=True, app_origin="http://localhost:3443").validate()
    for seconds in (0, 59, 1801, 86400):
        with pytest.raises(ValueError):
            Settings(mode="plain", database_url="sqlite://", testing=True, session_ttl=seconds).validate()


def test_env_configuration_does_not_implicitly_load_old_lab_dotenv(monkeypatch):
    monkeypatch.setenv("MODE", "plain")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    # Reading from env validates the production database, even if an old root .env exists.
    with pytest.raises(ValueError):
        Settings.from_env()


@pytest.mark.parametrize("role", ["analyst", "auditor", "admin", "public", "staff", "unknown"])
def test_policy_denies_record_detail_by_default(role):
    with pytest.raises(PermissionError):
        detail_policy(role)
    assert not can_edit(role)


def test_finance_does_not_gain_contact_edit_or_religion():
    finance = detail_policy("finance_officer")
    assert "rekening" in finance.fields and "npwp" in finance.fields
    assert not {"agama", "email", "handphone"} & finance.fields
    assert finance.masked == {"nama", "no_ktp"}
    assert not can_edit("finance_officer")


@pytest.mark.parametrize("role,expected", [
    ("operator", {"list", "search", "detail", "update"}),
    ("privileged_officer", {"list", "search", "detail", "update", "insert"}),
    ("finance_officer", {"list", "search", "detail"}),
    ("anggota", {"list", "search", "detail", "update"}),
    ("analyst", {"analytics"}),
    ("auditor", {"audit"}),
])
def test_policy_endpoint_capability_matrix(role, expected):
    actual = {action for action in ["list", "search", "detail", "update", "insert", "analytics", "audit"] if can_access(role, action)}
    assert actual == expected


@pytest.mark.parametrize("role", ["admin", "unknown"])
def test_unknown_role_has_no_endpoint_capability(role):
    assert not any(can_access(role, action) for action in ["list", "search", "detail", "update", "insert", "analytics", "audit"])


def test_unknown_actions_always_deny_even_for_privileged_roles():
    for role in ["operator", "privileged_officer", "finance_officer", "anggota", "analyst", "auditor"]:
        assert not can_access(role, "delete")
        assert not can_access(role, "unexpected-action")


def test_ownership_and_list_masking_follow_role_purpose():
    roles = ["operator", "privileged_officer", "finance_officer", "anggota", "analyst", "auditor"]
    assert {role for role in roles if owns_only(role)} == {"anggota"}
    assert {role for role in roles if mask_list_name(role)} == {"operator", "finance_officer"}


@pytest.mark.parametrize("value", ["", "1", "12", "123", "1234"])
def test_short_value_mask_never_leaks_complete_input(value):
    assert mask(value, "no_ktp") == "****"
    assert mask(None, "email") is None


def test_normalization_preserves_zeroes_and_username_case():
    assert normalized("no_ktp", "00.123-456 789012") == "00123456789012"
    assert normalized("email", "  Unit@Example.Test  ") == "unit@example.test"
    assert normalized("pengguna", "  CaseSensitive  ") == "CaseSensitive"


def test_non_module_a_crypto_factory_is_rejected():
    settings = SimpleNamespace(crypto_factory="untrusted_module:factory")
    with pytest.raises(ValueError):
        ToolkitAdapter(settings)


def test_missing_module_a_adapter_does_not_fallback(monkeypatch, tmp_path):
    ca = tmp_path / "trusted-ca.crt"
    ca.touch()
    settings = SimpleNamespace(crypto_factory="dprcrypto:create_service", openbao_addr="https://bao.example.test",
                               openbao_token=secrets.token_urlsafe(24), openbao_cacert=str(ca))
    monkeypatch.setattr("service_app.crypto.ssl.create_default_context", lambda **kwargs: object())
    def unavailable(name):
        raise ModuleNotFoundError(name)
    monkeypatch.setattr("service_app.crypto.importlib.import_module", unavailable)
    with pytest.raises(CryptoUnavailable):
        ToolkitAdapter(settings)


@pytest.mark.parametrize("missing", ["package", "profile", "vectors"])
def test_protected_startup_requires_all_shared_module_a_dependencies(monkeypatch, tmp_path, missing):
    import service_app.main as module
    module_path = tmp_path / "app/backend/service_app/main.py"
    monkeypatch.setattr(module, "__file__", str(module_path))
    if missing != "package":
        (tmp_path / "toolkit/dprcrypto").mkdir(parents=True)
    if missing != "profile":
        profile = tmp_path / "policy/protection_profile.yaml"
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.touch()
    if missing != "vectors":
        vectors = tmp_path / "docs/contracts/test_vectors.json"
        vectors.parent.mkdir(parents=True, exist_ok=True)
        vectors.write_text("{}", encoding="utf-8")
    settings = Settings(mode="protected", database_url="postgresql+psycopg://app_user@localhost/protected_100k")
    monkeypatch.setattr(settings, "validate", lambda: settings)
    def forbidden(*args, **kwargs):
        raise AssertionError("No toolkit or database call may occur before dependency gate")
    monkeypatch.setattr(module, "ToolkitAdapter", forbidden)
    monkeypatch.setattr(module, "create_engine", forbidden)
    with pytest.raises(CryptoUnavailable):
        module.create_app(settings)


def test_toolkit_contract_enforces_methods_and_fails_closed(monkeypatch, tmp_path):
    ca = tmp_path / "trusted-ca.crt"
    ca.touch()
    expected_token = secrets.token_urlsafe(24)
    expected_index = secrets.token_bytes(32)
    context = object()
    settings = SimpleNamespace(crypto_factory="dprcrypto:create_service", openbao_addr="https://bao.example.test",
                               openbao_token=expected_token, openbao_cacert=str(ca))
    monkeypatch.setattr("service_app.crypto.ssl.create_default_context", lambda **kwargs: context)
    calls = []
    class Driver:
        def blind_index(self, *args, **kwargs):
            calls.append((args, kwargs))
            return expected_index
        def unwrap_many(self, *args, **kwargs):
            raise RuntimeError("Synthetic failure")
        def decrypt_field(self, *args, **kwargs):
            raise RuntimeError("Synthetic failure")
        def encrypt_field(self, *args, **kwargs):
            raise RuntimeError("Synthetic failure")
        def new_record_keys(self, *args, **kwargs):
            raise RuntimeError("Synthetic failure")
    def factory(**kwargs):
        assert kwargs["openbao_addr"].startswith("https://")
        assert kwargs["token"] == expected_token and kwargs["ssl_context"] is context
        return Driver()
    monkeypatch.setattr("service_app.crypto.importlib.import_module", lambda name: SimpleNamespace(create_service=factory))
    adapter = ToolkitAdapter(settings)
    assert adapter.blind_index("email", "test@example.test") == expected_index
    assert len(calls) == 1
    with pytest.raises(CryptoUnavailable):
        adapter.unwrap_many("pii", [])
    with pytest.raises(AttributeError):
        adapter.export_key()
