"""Auditable type factors and the unchanged six-factor P0–P3 scale."""
import math
from pathlib import Path

import yaml


def load_type_policy(path=None):
    path = Path(path) if path else Path(__file__).parent / "config" / "impact.yaml"
    with path.open(encoding="utf-8") as handle:
        policy = yaml.safe_load(handle)
    if not isinstance(policy, dict) or set(policy) != {"default", "types"} or not isinstance(policy["types"], dict):
        raise ValueError("Invalid type policy")
    for factors in [policy["default"], *policy["types"].values()]:
        if not isinstance(factors, dict) or set(factors) != {"sensitivity", "impact"} or any(
            type(v) is not int or not 1 <= v <= 5 for v in factors.values()
        ):
            raise ValueError("Type factors must be integers from one to five")
    return policy


def rank(score):
    return "P0" if score >= 25 else "P1" if score >= 19 else "P2" if score >= 13 else "P3"


def priority_factors(kind, content, unique_ratio, environment, policy):
    typed = policy["types"].get(kind, policy["default"])
    exploitability = max(1, min(5, math.ceil(content / 25) + int(unique_ratio > 0.9 and content >= 60)))
    if kind in {"kategori", "operasional", "keluarga"}:
        exploitability = 1
    factors = {**typed, "exploitability": exploitability,
               **{key: environment[key] for key in ("volume", "exposure", "recovery")}}
    return factors
