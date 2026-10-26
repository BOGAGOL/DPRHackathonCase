"""Generate PUBLIC synthetic test vectors and verify them without printing material."""

import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .bidx import index_message, normalize
from .codec import build_aad, decrypt, encrypt
from .errors import CryptoError, DecryptionError


def generate_file(path: Path) -> None:
    # Contract section 9 explicitly requires PUBLIC, non-production example keys.
    # Never reads credentials, source dumps, or production DEKs from the environment.
    identity = str(uuid4())
    pii, finance, search = os.urandom(32), os.urandom(32), os.urandom(32)
    fields = []
    for column, plaintext, domain in (
        ("nama", "Anggota Uji Ω", "PII"), ("no_ktp", "00112233445566", "PII"),
        ("tanggal_lahir", "1985-06-17", "PII"), ("rekening", "0000111122223333", "FIN"),
        ("email", "", "PII"), ("tanggal_pernikahan", None, "PII"),
    ):
        dek = pii if domain == "PII" else finance
        blob = encrypt(plaintext, dek, column=column, anggota_id=identity)
        aad = build_aad(column, identity)
        fields.append({"domain": domain, "column": column, "anggota_id": identity,
            "protection_version": 1, "dek_hex": dek.hex(), "plaintext": plaintext,
            "aad_utf8": aad.decode(), "aad_hex": aad.hex(),
            "nonce_hex": None if blob is None else blob[1:13].hex(),
            "blob_hex": None if blob is None else blob.hex()})
    cases = []
    for column, value in (("no_ktp", " 0011-2233 445566 "), ("email", "  UJI@Example.TEST  "),
                           ("pengguna", "  Uji_001  "), ("email", None), ("pengguna", "")):
        message = index_message(column, value)
        cases.append({"column": column, "input": value, "normalized": normalize(column, value),
            "message_utf8": None if message is None else message.decode(),
            "bidx_hex": None if message is None else hmac.new(search, message, hashlib.sha256).hexdigest()})
    document = {"format": "dpr-contract-v1", "test_only": True,
        "warning": "PUBLIC synthetic test keys. NEVER use these keys to protect data.",
        "algorithm": "AES-256-GCM", "fields": fields,
        "blind_index": {"search_key_hex": search.hex(), "cases": cases}}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def verify_document(document: dict) -> dict[str, bool]:
    if (document.get("test_only") is not True or document.get("format") != "dpr-contract-v1"
            or document.get("algorithm") != "AES-256-GCM"):
        raise CryptoError("Expected public contract v1 test vectors")
    checks = {"aad": True, "blob_and_roundtrip": True, "tamper_rejected": True,
              "record_swap_rejected": True, "column_swap_rejected": True,
              "nonce_randomness_sample": True, "normalization": True, "bidx": True}
    if not document["fields"] or not document["blind_index"]["cases"]:
        raise CryptoError("Empty test vectors")
    for item in document["fields"]:
        dek = bytes.fromhex(item["dek_hex"])
        blob = None if item["blob_hex"] is None else bytes.fromhex(item["blob_hex"])
        kwargs = {"column": item["column"], "anggota_id": item["anggota_id"], "protection_version": item["protection_version"]}
        aad = build_aad(**kwargs)
        checks["aad"] &= aad == item["aad_utf8"].encode() == bytes.fromhex(item["aad_hex"])
        checks["blob_and_roundtrip"] &= decrypt(blob, dek, **kwargs) == item["plaintext"]
        if blob is None:
            checks["blob_and_roundtrip"] &= item["plaintext"] is None and item["nonce_hex"] is None
            continue
        nonce = bytes.fromhex(item["nonce_hex"])
        reference = b"\x01" + nonce + AESGCM(dek).encrypt(nonce, item["plaintext"].encode(), aad)
        checks["blob_and_roundtrip"] &= blob == reference and len(nonce) == 12
        fresh = [encrypt(item["plaintext"], dek, **kwargs)[1:13] for _ in range(64)]
        checks["nonce_randomness_sample"] &= len(set(fresh)) == 64
        tampered = bytearray(blob)
        tampered[-1] ^= 1
        for name, candidate, context in (
            ("tamper_rejected", bytes(tampered), kwargs),
            ("record_swap_rejected", blob, {**kwargs, "anggota_id": str(uuid4())}),
            ("column_swap_rejected", blob, {**kwargs, "column": "rekening" if item["column"] != "rekening" else "email"}),
        ):
            try:
                decrypt(candidate, dek, **context)
                checks[name] = False
            except DecryptionError:
                pass
    search = bytes.fromhex(document["blind_index"]["search_key_hex"])
    if len(search) != 32:
        raise CryptoError("Invalid public test key length")
    for item in document["blind_index"]["cases"]:
        message = index_message(item["column"], item["input"])
        checks["normalization"] &= normalize(item["column"], item["input"]) == item["normalized"]
        checks["bidx"] &= (None if message is None else message.decode()) == item["message_utf8"]
        digest = None if message is None else hmac.new(search, message, hashlib.sha256).hexdigest()
        checks["bidx"] &= digest == item["bidx_hex"]
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "verify"))
    parser.add_argument("--vectors", type=Path, default=Path("docs/contracts/test_vectors.json"))
    parser.add_argument("--evidence", type=Path, default=Path("evidence/crypto/vectors.json"))
    args = parser.parse_args()
    if args.command == "generate":
        generate_file(args.vectors)
        print("Public synthetic test vectors generated; no production material used.")
        return
    report = {"schema_version": 1, "passed": False, "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        raw = args.vectors.read_bytes()
        checks = verify_document(json.loads(raw.decode("utf-8")))
        report.update(checks=checks, passed=all(checks.values()), vectors_sha256=hashlib.sha256(raw).hexdigest())
    except (CryptoError, ValueError, TypeError, KeyError, OSError):
        report["error"] = "invalid_test_vectors"
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Contract vector verification: " + ("PASS" if report["passed"] else "FAIL"))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
