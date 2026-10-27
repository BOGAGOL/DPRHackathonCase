"""Contract baseline scope and a fail-closed handoff to Module A's real profile."""
from pathlib import Path

import yaml

from datagen.model import COLUMNS

ROOT = Path(__file__).resolve().parents[1]
REF = ("jenis_kelamin", "pekerjaan_terakhir", "nama_kppn", "nama_bank")
FIN = ("rekening", "nama_rekening", "npwp", "kode_bank")
SENSITIVE = tuple(c for c in COLUMNS[1:] if c not in REF)
PII = tuple(c for c in SENSITIVE if c not in FIN)
# Frozen before simulation; names/contacts identify or enable direct contact.
# Surrogate id and room are excluded from DIE; room remains in ESCE scope.
DIRECT = ("nama", "nama_lengkap", "nama_tanpa_gelar", "nama_rekening", "no_ktp",
          "npwp", "nip_kppn", "rekening", "email", "pengguna", "handphone", "telpon_jakarta", "telpon_daerah")
SCENARIOS = ("baseline_dump", "protected_dump_no_key", "protected_dump_with_pii_key",
             "protected_dump_with_finance_key", "protected_dump_with_search_key", "backup_artifact_no_key")


class PendingProtection(Exception):
    """Protected evidence is unavailable, never zero exposure by assumption."""


def protection_plan(scenario, path=None):
    if scenario not in SCENARIOS:
        raise ValueError("Unknown leakage scenario")
    path = Path(path) if path else ROOT / "policy/protection_profile.yaml"
    if scenario == "baseline_dump":
        return {"scenario": scenario, "profile_source": "CONTRACT.md section 3 (baseline only)",
                "sensitive": list(SENSITIVE), "domains": {"PII": list(PII), "FIN": list(FIN)},
                "plaintext": list(COLUMNS[1:]), "direct_identifiers": list(DIRECT), "bidx": [],
                "requires_decryption_hook": False}
    if not path.is_file():
        raise PendingProtection("Waiting for policy/protection_profile.yaml from Module A in integrated tree")
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    columns = profile.get("columns", {})
    if (profile.get("protection_version") != 1 or profile.get("null_policy") != "preserve_null"
            or set(columns) != set(COLUMNS[1:])):
        raise ValueError("Protection profile incompatible with contract v1")
    for name, config in columns.items():
        domain = "FIN" if name in FIN else "PII" if name in PII else None
        if config.get("domain") != domain or config.get("aead") is not (name in SENSITIVE):
            raise ValueError("Protection profile domain/AEAD conflicts with contract")
        if config.get("storage_column") != (name + "_ct" if name in SENSITIVE else name):
            raise ValueError("Unsupported protection storage mapping")
    domain = {"protected_dump_with_pii_key": "PII", "protected_dump_with_finance_key": "FIN"}.get(scenario)
    return {"scenario": scenario, "profile_source": "policy/protection_profile.yaml", "profile_version": profile.get("profile_version"),
            "sensitive": list(SENSITIVE), "domains": {"PII": list(PII), "FIN": list(FIN)},
            "plaintext": [name for name, cfg in columns.items() if not cfg["aead"]],
            "storage_columns": {name: cfg["storage_column"] for name, cfg in columns.items()},
            "bidx": [cfg["bidx_column"] for cfg in columns.values() if cfg.get("bidx")],
            "authorized_decrypt_domain": domain, "requires_decryption_hook": bool(domain),
            "search_key_only": scenario == "protected_dump_with_search_key",
            "direct_identifiers": list(DIRECT)}
