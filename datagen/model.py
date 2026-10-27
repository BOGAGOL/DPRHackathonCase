"""Pure generator and aggregate validation. Never emit source values."""

from collections import Counter, defaultdict
from datetime import date, timedelta
import hashlib
import json
import math
import random
import re
import string

COLUMNS = (
    "id", "nama", "nama_lengkap", "nama_tanpa_gelar", "jenis_kelamin", "tempat_lahir",
    "tanggal_lahir", "tanggal_pernikahan", "no_ktp", "pekerjaan_terakhir", "alamat_jakarta",
    "telpon_jakarta", "alamat_daerah", "telpon_daerah", "handphone", "email", "ruangan",
    "status_kawin", "jumlah_anak", "jumlah_tanggungan", "jumlah_jiwa", "rekening",
    "nama_rekening", "npwp", "nama_kppn", "nip_kppn", "nama_bank", "kode_bank", "pengguna", "agama",
)
NUMBERS = {"no_ktp": ("0", 14), "rekening": ("0", 16), "npwp": ("0", 15),
           "nip_kppn": ("0", 18), "handphone": ("081", 10), "telpon_daerah": ("0", 10)}
UNIQUE = (*NUMBERS, "email", "pengguna", "ruangan")
CATEGORICAL = ("jenis_kelamin", "tempat_lahir", "pekerjaan_terakhir", "status_kawin",
               "agama", "nama_bank", "nama_kppn", "jumlah_anak")
REFERENCE_DATE = date(2026, 10, 1)


def anniversary(born, years):
    """Clamp leap day to Feb 28 for interval validation."""
    try:
        return born.replace(year=born.year + years)
    except ValueError:
        return born.replace(year=born.year + years, day=28)


def marriage_kind(row):
    born, married = row["tanggal_lahir"], row["tanggal_pernikahan"]
    if married is None:
        return "null"
    if married < born:
        return "before_birth"
    return "under_17" if married < anniversary(born, 17) else "adult"


def canonical(row):
    return (json.dumps([row[c] for c in COLUMNS], default=str, ensure_ascii=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def checksum(rows):
    # One digest for the entire ordered dataset, never hashes of low-entropy cells.
    digest = hashlib.sha256()
    for row in rows:
        digest.update(canonical(row))
    return digest.hexdigest()


def number_stream(prefix, width, rng, occupied):
    """Affine permutation: no collisions, including against retained source IDs."""
    modulus = 10 ** (width - len(prefix))
    multiplier = rng.randrange(1, modulus)
    while math.gcd(multiplier, modulus) != 1:
        multiplier = (multiplier + 1) % modulus or 1
    offset = rng.randrange(modulus)
    for i in range(modulus):
        value = prefix + str((multiplier * i + offset) % modulus).zfill(width - len(prefix))
        if value not in occupied:
            occupied.add(value)
            yield value
    raise ValueError("Identifier namespace exhausted")


def learn(source):
    if not source or any(set(row) != set(COLUMNS) for row in source):
        raise ValueError("Source schema/rows invalid")
    birthdays = [r["tanggal_lahir"] for r in source]
    if any(not isinstance(d, date) or d > REFERENCE_DATE for d in birthdays):
        raise ValueError("Source birth dates invalid")
    codes = defaultdict(Counter)
    for row in source:
        codes[row["nama_bank"]][row["kode_bank"]] += 1
    return {"birth_min": min(birthdays), "birth_max": max(birthdays),
            "modal_codes": {bank: counts.most_common(1)[0][0] for bank, counts in codes.items()},
            "name_lengths": [max(24, min(48, len(r["nama"]))) for r in source]}


def generate(source, total, seed=42, replicate_anomalies=True):
    """Retain source; cycle shuffled templates for joint categorical distribution."""
    profile = learn(source)
    if total < len(source) or len({r["id"] for r in source}) != len(source):
        raise ValueError("Invalid row count/source IDs")
    source = sorted(source, key=lambda r: r["id"])
    yield from (dict(row) for row in source)
    rng = random.Random(seed)
    used = {c: {r[c] for r in source} for c in UNIQUE}
    streams = {c: number_stream(prefix, width, rng, used[c]) for c, (prefix, width) in NUMBERS.items()}
    forbidden_names = {r["nama"] for r in source}
    last_id = max(r["id"] for r in source)
    room_number = max((int(re.search(r"(\d+)$", r["ruangan"])[1]) for r in source), default=0)
    order = []
    for i in range(total - len(source)):
        if i % len(source) == 0:
            order = list(range(len(source)))
            rng.shuffle(order)
        template = source[order[i % len(source)]]
        row = {c: template[c] for c in COLUMNS}
        row["id"] = last_id + i + 1
        while True:
            name = "".join(rng.choice(string.ascii_letters + "'.,-")
                           for _ in range(rng.choice(profile["name_lengths"])))
            if name not in forbidden_names:
                break
        row.update(nama=name, nama_lengkap=name, nama_tanpa_gelar=name, nama_rekening=name[:20])
        born = profile["birth_min"] + timedelta(days=rng.randrange(
            (profile["birth_max"] - profile["birth_min"]).days + 1))
        row["tanggal_lahir"] = born
        kind = marriage_kind(template) if replicate_anomalies else "adult"
        if row["status_kawin"] != "K":
            row["tanggal_pernikahan"] = None
        else:
            if kind == "before_birth":
                start, end = born - timedelta(days=3650), born - timedelta(days=1)
            elif kind == "under_17":
                start, end = born, anniversary(born, 17) - timedelta(days=1)
            else:
                start, end = anniversary(born, 17), REFERENCE_DATE
            if start > end:
                raise ValueError("Source range cannot support marriage relationship")
            row["tanggal_pernikahan"] = start + timedelta(days=rng.randrange((end - start).days + 1))
            row["jumlah_tanggungan"] = row["jumlah_anak"] + 1
        row["jumlah_jiwa"] = row["jumlah_tanggungan"] + 1
        for col, stream in streams.items():
            row[col] = next(stream)
        room_number += 1
        while f"DUMMY-{room_number}" in used["ruangan"]:
            room_number += 1
        row["ruangan"] = f"DUMMY-{room_number}"
        used["ruangan"].add(row["ruangan"])
        normalized = re.sub("[^a-z]", "", name.lower()) or "synthetic"
        row["email"] = f"{normalized}{room_number}@example.com"
        row["pengguna"] = f"dummy_{normalized}{room_number}"
        if any(row[c] in used[c] for c in ("email", "pengguna")):
            raise ValueError("Generated identifier collision")
        for col in ("email", "pengguna"):
            used[col].add(row[col])
        row["telpon_jakarta"] = "021" + str(rng.randrange(10**8)).zfill(8)
        row["alamat_jakarta"] = f"Jl. Contoh No. {room_number}, Jakarta"
        row["alamat_daerah"] = f"Jl. Contoh No. {room_number}, {row['tempat_lahir']}"
        if not replicate_anomalies:
            row["kode_bank"] = profile["modal_codes"][row["nama_bank"]]
        yield row


def validate(rows, source, total, replicate_anomalies=True):
    """Streaming full-table checks; output only counts, flags, aggregate digests."""
    profile = learn(source)
    source_ids = {r["id"] for r in source}
    seen = {c: set() for c in ("id", *UNIQUE)}
    duplicates = Counter()
    formats, relations = Counter(), Counter()
    groups = {"source": 0, "synthetic": 0}
    anomalies = {group: Counter() for group in groups}
    categories = {c: Counter() for c in CATEGORICAL}
    digest, original_digest = hashlib.sha256(), hashlib.sha256()
    for row in rows:
        digest.update(canonical(row))
        original = row["id"] in source_ids
        group = "source" if original else "synthetic"
        groups[group] += 1
        if original:
            original_digest.update(canonical(row))
        for col, values in seen.items():
            value = row[col]
            if value is None or value in values:
                duplicates[col] += 1
            values.add(value)
        anomalies[group][marriage_kind(row)] += 1
        if row["kode_bank"] != profile["modal_codes"][row["nama_bank"]]:
            anomalies[group]["bank_nonmodal"] += 1
        if original:
            continue
        for col in CATEGORICAL:
            categories[col][row[col]] += 1
        for col, (prefix, width) in NUMBERS.items():
            if re.fullmatch(re.escape(prefix) + r"\d{" + str(width - len(prefix)) + "}", row[col]) is None:
                formats[col] += 1
        for col, pattern in {"telpon_jakarta": r"021\d{8}", "ruangan": r"DUMMY-\d+",
                             "email": r"[a-z]+\d+@example\.com", "pengguna": r"dummy_[a-z]+\d+"}.items():
            if re.fullmatch(pattern, row[col]) is None:
                formats[col] += 1
        checks = {
            "names_equal": row["nama"] == row["nama_lengkap"] == row["nama_tanpa_gelar"],
            "account_name_prefix": row["nama_rekening"] == row["nama"][:20],
            "address_city": row["alamat_daerah"].endswith(", " + row["tempat_lahir"]),
            "household_offset": row["jumlah_jiwa"] == row["jumlah_tanggungan"] + 1,
            "marriage_presence": (row["status_kawin"] == "K") == (row["tanggal_pernikahan"] is not None),
            "married_dependents": row["status_kawin"] != "K" or row["jumlah_tanggungan"] == row["jumlah_anak"] + 1,
            "birthday_range": profile["birth_min"] <= row["tanggal_lahir"] <= profile["birth_max"],
            "room_link": row["email"].split("@")[0].endswith(row["ruangan"].split("-")[-1])
                         and row["pengguna"].endswith(row["ruangan"].split("-")[-1]),
            "name_links": row["email"].split("@")[0] ==
                          (re.sub("[^a-z]", "", row["nama"].lower()) or "synthetic") + row["ruangan"].split("-")[-1]
                          and row["pengguna"] == "dummy_" + row["email"].split("@")[0],
        }
        for key, ok in checks.items():
            if not ok:
                relations[key] += 1
    distributions = {}
    n = groups["synthetic"]
    for col, counts in categories.items():
        original_counts = Counter(r[col] for r in source)
        keys = counts.keys() | original_counts.keys()
        # Each source template appears floor(n/s) or ceil(n/s) times: at most one partial cycle.
        max_error = max((abs(counts[k] - n * original_counts[k] / len(source)) for k in keys), default=0)
        distributions[col] = {"categories": len(keys), "max_count_deviation": max_error,
                              "within_one_source_cycle": max_error <= len(source)}
    source_equal = groups["source"] == len(source) and original_digest.hexdigest() == checksum(source)
    anomaly_deviations = {k: abs(anomalies["synthetic"][k] - n * anomalies["source"][k] / len(source))
                          for k in ("before_birth", "under_17", "bank_nonmodal")}
    anomaly_ok = (all(v <= len(source) for v in anomaly_deviations.values()) if replicate_anomalies
                  else not any(anomalies["synthetic"][k] for k in anomaly_deviations))
    return {"passed": groups["source"] + n == total and source_equal and not duplicates
                      and not formats and not relations and anomaly_ok
                      and all(d["within_one_source_cycle"] for d in distributions.values()),
            "row_count": sum(groups.values()), "groups": groups, "source_preserved": source_equal,
            "duplicate_or_null_counts": dict(duplicates), "synthetic_format_violations": dict(formats),
            "synthetic_relation_violations": dict(relations), "distributions": distributions,
            "anomalies": {k: dict(v) for k, v in anomalies.items()},
            "anomaly_policy_valid": anomaly_ok, "anomaly_count_deviations": anomaly_deviations,
            "checksum_sha256": digest.hexdigest(),
            "source_checksum_sha256": original_digest.hexdigest()}
