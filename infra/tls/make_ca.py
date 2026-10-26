"""Create a local self-signed CA and a CA-signed OpenBao server certificate."""

from datetime import datetime, timedelta, timezone
import ipaddress
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from infra.security import external_directory, secure_directory, write_private


def make_ca(directory: Path) -> None:
    directory = secure_directory(directory)
    targets = ("ca.key", "ca.crt", "server.key", "server.crt")
    if any((directory / name).exists() for name in targets):
        raise ValueError("TLS material already exists; use an explicit certificate renewal procedure")
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DPR local development CA")])
    ca_cert = (
        x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "openbao")]))
        .issuer_name(ca_name).public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"), x509.DNSName("openbao"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            x509.IPAddress(ipaddress.ip_address("::1")),
        ]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    for name, key in (("ca.key", ca_key), ("server.key", server_key)):
        write_private(directory / name, key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
    for name, cert in (("ca.crt", ca_cert), ("server.crt", server_cert)):
        write_private(directory / name, cert.public_bytes(serialization.Encoding.PEM))


def main() -> None:
    try:
        root = secure_directory(external_directory(os.environ.get("DPR_SECRETS_DIR")))
        make_ca(root / "tls")
    except (ValueError, RuntimeError, OSError):
        raise SystemExit("TLS setup failed; check the external directory and existing material") from None
    print("Local CA and 30-day server certificate created outside the repository.")
    print("WARNING: protect the CA private key; trust this CA only for this development lab.")


if __name__ == "__main__":
    main()
