import ipaddress
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
import pytest
import yaml

from infra.security import REPO, external_directory, secure_directory, write_private
from infra.tls.make_ca import main, make_ca


@pytest.mark.parametrize("value", [None, "relative", str(REPO), str(REPO / "secrets"), str(REPO.parent), str(Path.home())])
def test_reject_unsafe_secrets_directory(value):
    with pytest.raises(ValueError):
        external_directory(value)


def test_external_path_and_exclusive_permissions(tmp_path):
    directory = secure_directory(external_directory(str(tmp_path / "private")))
    write_private(directory / "material", os.urandom(32))
    with pytest.raises(FileExistsError):
        write_private(directory / "material", b"")
    if os.name != "nt":
        assert directory.stat().st_mode & 0o777 == 0o700
        assert (directory / "material").stat().st_mode & 0o777 == 0o600
    else:
        import subprocess
        result = subprocess.run(["icacls", str(directory)], capture_output=True, text=True, check=True)
        assert "(I)" not in result.stdout


def test_ca_chain_san_key_and_no_overwrite(tmp_path):
    make_ca(tmp_path)
    ca = x509.load_pem_x509_certificate((tmp_path / "ca.crt").read_bytes())
    server = x509.load_pem_x509_certificate((tmp_path / "server.crt").read_bytes())
    ca.public_key().verify(server.signature, server.tbs_certificate_bytes, padding.PKCS1v15(), server.signature_hash_algorithm)
    ca.public_key().verify(ca.signature, ca.tbs_certificate_bytes, padding.PKCS1v15(), ca.signature_hash_algorithm)
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert not server.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    san = server.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert set(san.get_values_for_type(x509.DNSName)) == {"localhost", "openbao"}
    assert ipaddress.ip_address("127.0.0.1") in san.get_values_for_type(x509.IPAddress)
    key = serialization.load_pem_private_key((tmp_path / "server.key").read_bytes(), password=None)
    assert key.public_key().public_numbers() == server.public_key().public_numbers()
    assert (server.not_valid_after_utc - server.not_valid_before_utc).days == 30
    with pytest.raises(ValueError):
        make_ca(tmp_path)


def test_tls_entrypoint(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DPR_SECRETS_DIR", str(tmp_path))
    main()
    assert (tmp_path / "tls/server.key").exists()
    assert "WARNING" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main()


def test_compose_tls_and_database_isolation():
    compose = yaml.safe_load((REPO / "infra/compose.yaml").read_text())
    bao = compose["services"]["openbao"]
    assert bao["image"] == "openbao/openbao:2.5.5"
    assert bao["environment"]["BAO_ADDR"].startswith("https://")
    assert all("127.0.0.1:" in port for port in bao["ports"])
    sources = [v["source"] for v in bao["volumes"] if isinstance(v, dict)]
    assert not any("ca.key" in v or "bootstrap" in v for v in sources)
    assert all(v["read_only"] and not v["bind"]["create_host_path"] for v in bao["volumes"] if isinstance(v, dict))
    config = (REPO / "infra/openbao/openbao.hcl").read_text()
    assert "tls_disable = false" in config and 'tls_min_version = "tls12"' in config
    pg = compose["services"]["postgres"]
    assert pg["image"] == "postgres:18" and pg["profiles"] == ["new-postgres"]
    assert pg["volumes"] == ["postgres_data:/var/lib/postgresql"]
    assert "5434" in pg["ports"][0]
