"""Issue a PostgreSQL leaf certificate using the external local development CA."""

import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from infra.security import external_directory, secure_directory, write_private


def make_certificate(root: Path, *, dns_names: tuple[str, ...] = (), ip_addresses: tuple[str, ...] = ()) -> Path:
    root = external_directory(str(root))
    destination = secure_directory(root / "postgres" / "tls")
    if any((destination / name).exists() for name in ("ca.crt", "server.crt", "server.key")):
        raise ValueError("PostgreSQL TLS material exists; refusing to overwrite it")
    ca = x509.load_pem_x509_certificate((root / "tls/ca.crt").read_bytes())
    ca_key = serialization.load_pem_private_key((root / "tls/ca.key").read_bytes(), password=None)
    now = datetime.now(timezone.utc)
    if (not isinstance(ca_key, rsa.RSAPrivateKey)
            or ca.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            != ca_key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            or not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
            or not ca.not_valid_before_utc <= now < ca.not_valid_after_utc - timedelta(days=1)):
        raise ValueError("Invalid or expired local CA")
    names = tuple(dict.fromkeys(("pg-dpr", "localhost", "host.docker.internal", *dns_names)))
    if any(not name or len(name) > 253 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for char in name) for name in names):
        raise ValueError("Invalid PostgreSQL DNS SAN")
    ips = tuple(dict.fromkeys(("127.0.0.1", "::1", *ip_addresses)))
    sans = [x509.DNSName(name) for name in names] + [x509.IPAddress(ipaddress.ip_address(value)) for value in ips]
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    certificate = (
        x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "pg-dpr")]))
        .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(min(now + timedelta(days=30), ca.not_valid_after_utc))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName(sans), critical=False).sign(ca_key, hashes.SHA256())
    )
    write_private(destination / "server.key", key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    write_private(destination / "server.crt", certificate.public_bytes(serialization.Encoding.PEM))
    write_private(destination / "ca.crt", ca.public_bytes(serialization.Encoding.PEM))
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dns-name", action="append", default=[])
    parser.add_argument("--ip-address", action="append", default=[])
    args = parser.parse_args()
    try:
        root = secure_directory(external_directory(os.environ.get("DPR_SECRETS_DIR")))
        make_certificate(root, dns_names=tuple(args.dns_name), ip_addresses=tuple(args.ip_address))
    except (ValueError, OSError, RuntimeError):
        raise SystemExit("PostgreSQL certificate setup failed; check external CA, SANs, and existing material") from None
    print("PostgreSQL certificate issued outside the repository; private CA key remains outside the container.")


if __name__ == "__main__":
    main()
