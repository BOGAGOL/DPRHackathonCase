"""Interpretable column features. Names cannot independently pass auto_accept."""
from collections import Counter
from datetime import date
import math
import re

from .masking import mask
from .priority import load_type_policy, priority_factors, rank


PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "telepon": re.compile(r"(?:\+62|62|0)[2-9][0-9 ()-]{6,13}[0-9]"),
    "nik": re.compile(r"[0-9]{16}"),
    "npwp": re.compile(r"(?:\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}|\d{15})"),
    "rekening": re.compile(r"\d{10,19}"),
    "tanggal": re.compile(r"\d{4}-\d{2}-\d{2}(?:[ T].*)?|\d{2}[/.-]\d{2}[/.-]\d{4}"),
    "kode_pos": re.compile(r"\d{5}"),
    "alamat": re.compile(r"\b(?:jl\.?|jalan|no\.|rt\b|rw\b|kel\.|kec\.)", re.I),
    "nama": re.compile(r"[^\W\d_]{2,}(?:[ .'-]+[^\W\d_]{2,}){1,5}", re.UNICODE),
}
NAMES = {
    "email": ("email", "e_mail", "surel"),
    "telepon": ("hp", "handphone", "telp", "telpon", "telepon", "phone", "mobile", "fax"),
    "nik": ("ktp", "no_ktp", "nik", "kependudukan", "noktp", "nomornik"),
    "npwp": ("npwp", "tax_id"),
    "rekening": ("rek", "rekening", "account", "kartu", "card", "iban"),
    "nama": ("nama", "name"),
    "alamat": ("alamat", "address"),
    "tanggal_lahir": ("lahir", "birth", "dob"),
    "tanggal_pernikahan": ("tanggal_pernikahan", "wedding_date", "marriage_date", "pernikahan", "nikah", "wedding"),
    "tempat_lahir": ("tempat_lahir", "birthplace", "kota", "city"),
    "agama": ("agama", "religion"),
    "jenis_kelamin": ("gender", "sex", "kelamin"),
    "status_perkawinan": ("kawin", "marital", "pernikahan"),
    "keluarga": ("ibu", "anak", "keluarga", "tanggungan", "jiwa", "family", "child"),
    "kesehatan": ("sakit", "diagnosa", "diagnosis", "health", "medis"),
    "biometrik": ("biometrik", "biometric", "sidik", "fingerprint"),
    "genetika": ("genetika", "genetic", "dna"),
    "kejahatan": ("kejahatan", "criminal", "pidana"),
    "password": ("password", "passwd", "sandi", "pwd"),
    "identifier_lain": ("id", "nip", "pengguna", "username", "user", "kode"),
    "operasional": ("ruangan", "room", "kppn", "bank", "pekerjaan", "job"),
}
DICTIONARIES = {
    "agama": {"islam", "kristen", "protestan", "katolik", "hindu", "buddha", "budha", "konghucu", "kepercayaan"},
    "bank": {"bca", "bni", "bri", "btn", "mandiri", "bsi", "cimb", "danamon", "permata", "bank mandiri", "bank bca"},
    "jenis_kelamin": {"l", "p", "m", "f", "pria", "wanita", "laki-laki", "perempuan", "male", "female"},
    "status_perkawinan": {"k", "bk", "tk", "kawin", "belum kawin", "menikah", "single", "married", "cerai", "janda", "duda"},
    "kota": {"jakarta", "bandung", "surabaya", "semarang", "yogyakarta", "medan", "makassar", "bogor", "depok", "bekasi", "denpasar", "palembang", "malang", "solo", "padang", "aceh"},
    "kesehatan": {"diabetes", "hipertensi", "kanker", "asma", "hiv", "tuberkulosis"},
}


def name_scores(column):
    text = re.sub(r"[^a-z0-9]+", "_", column.lower()).strip("_")
    parts = text.split("_")
    scores = {kind: 100 if any(word in parts or ("_" in word and word in text)
                              for word in words) else 0 for kind, words in NAMES.items()}
    # Compound Indonesian names and common English compounds.
    for kind in ("telepon", "tanggal_lahir", "tanggal_pernikahan", "status_perkawinan"):
        if any(len(word) > 3 and word in text for word in NAMES[kind]):
            scores[kind] = 100
    if scores["nama"]:
        scores["rekening"] = 0  # Account holder name is a name, not an account number.
        if "bank" in parts or "kppn" in parts:
            scores["nama"] = 0
    if any(w in parts for w in ("tempat", "place")) and scores["tanggal_lahir"]:
        scores["tanggal_lahir"] = 0
        scores["tempat_lahir"] = 100
    return scores


def valid_nik(value):
    """Structural plausibility only; not an authoritative NIK validator."""
    if not PATTERNS["nik"].fullmatch(value) or len(set(value)) < 5:
        return False
    day, month = int(value[6:8]), int(value[8:10])
    day = day - 40 if day > 40 else day
    return 11 <= int(value[:2]) <= 94 and 1 <= day <= 31 and 1 <= month <= 12


def valid_date(value):
    try:
        if re.match(r"\d{4}-", value):
            date.fromisoformat(value[:10])
        else:
            d, m, y = re.split(r"[/.-]", value)
            date(int(y), int(m), int(d))
        return True
    except (ValueError, TypeError):
        return False


def embedded_findings(text):
    """Return internal matches; callers MUST mask each match before serialization."""
    findings = []
    for kind in ("email", "telepon", "nik", "npwp", "rekening"):
        pattern = PATTERNS[kind]
        for match in pattern.finditer(text):
            start, end = match.span()
            if (start and text[start - 1].isalnum()) or (end < len(text) and text[end].isalnum()):
                continue
            if kind == "telepon" and len(re.sub(r"\D", "", match.group())) > 14:
                continue
            # Ambiguous 16 digits remain an identifier candidate, not confirmed NIK.
            detected = "identifier_lain" if kind == "nik" and not valid_nik(match.group()) else kind
            findings.append((detected, match.group()))
    return findings


def features(values):
    nonnull = [str(v).strip() for v in values if v is not None and str(v).strip()]
    count = len(nonnull)
    denominator = count or 1
    lengths = Counter(map(len, nonnull))
    digit_ratios = [sum(c.isdecimal() for c in v) / max(1, len(v)) for v in nonnull]
    regex = {}
    for kind, pattern in PATTERNS.items():
        regex[kind] = sum(bool(pattern.search(v) if kind == "alamat" else pattern.fullmatch(v))
                          for v in nonnull) / denominator
    regex["tanggal"] = sum(bool(PATTERNS["tanggal"].fullmatch(v)) and valid_date(v)
                           for v in nonnull) / denominator
    dictionaries = {kind: sum(v.lower() in words for v in nonnull) / denominator
                    for kind, words in DICTIONARIES.items()}
    dictionaries["bank"] = sum(v.lower().removeprefix("bank ").strip() in DICTIONARIES["bank"]
                               for v in nonnull) / denominator
    dictionaries["government_office"] = sum(bool(re.match(
        r"^(?:kppn|kantor\s+pelayanan\s+perbendaharaan\s+negara)\b", v, re.I))
        for v in nonnull) / denominator
    embedded = Counter(kind for v in nonnull for kind in set(k for k, _ in embedded_findings(v)))
    entropy = []
    for v in nonnull:
        digits = re.sub(r"\D", "", v)
        counts = Counter(digits)
        entropy.append(-sum((n / len(digits)) * math.log2(n / len(digits)) for n in counts.values()) if digits else 0)
    return {
        "sample_rows": len(values), "nonnull": count,
        "null_ratio": 1 - count / max(1, len(values)),
        "unique_count": len(set(nonnull)), "unique_ratio": len(set(nonnull)) / denominator,
        "digit_ratio": sum(digit_ratios) / denominator,
        "fixed_length_ratio": max(lengths.values(), default=0) / denominator,
        "min_length": min(lengths, default=0), "max_length": max(lengths, default=0),
        "length_histogram": dict(lengths),
        "leading_zero_ratio": sum(v.startswith("0") for v in nonnull) / denominator,
        "charset_ratios": {"digits": sum(v.isdecimal() for v in nonnull) / denominator,
                           "letters": sum(v.isalpha() for v in nonnull) / denominator,
                           "ascii": sum(v.isascii() for v in nonnull) / denominator},
        "digit_entropy": sum(entropy) / denominator,
        "nik_plausible_ratio": sum(valid_nik(v) for v in nonnull) / denominator,
        "regex_ratios": regex, "dictionary_ratios": dictionaries,
        "embedded_ratios": {k: n / denominator for k, n in embedded.items()},
    }


def classify(column, values, config, environment, bank_context=False, baseline=False,
             data_type=None, conditional_presence=None):
    f = features(values)
    ns = name_scores(column)
    password_column = bool(ns["password"])
    parts = set(re.sub(r"[^a-z0-9]+", "_", column.lower()).split("_"))
    family_count = bool(ns["keluarga"] and parts & {"jumlah", "count", "total", "number", "num"}
                        and f["nonnull"] and f["charset_ratios"]["digits"] == 1)
    low_cardinality = f["unique_ratio"] < 0.2 or f["unique_count"] <= 20
    integer_storage = bool(data_type and re.fullmatch(r"(?:smallint|bigint|integer|int[248]?|serial|bigserial)", data_type, re.I))
    numeric_values = ([int(str(v)) for v in values if v is not None and str(v).isascii() and str(v).isdecimal()]
                      if column.lower() == "id" and integer_storage else [])
    surrogate_id = (column.lower() == "id" and integer_storage and len(numeric_values) >= 3
                    and len(numeric_values) == len(values) == len(set(numeric_values))
                    and max(numeric_values) - min(numeric_values) + 1 == len(numeric_values))
    rx, dictionaries = f["regex_ratios"], f["dictionary_ratios"]
    scores = {kind: 100 * rx[kind] for kind in ("email", "telepon", "npwp", "alamat", "nama")}
    negatives = []
    scores["tanggal_lahir"] = 90 * rx["tanggal"]
    scores["nik"] = 100 * f["nik_plausible_ratio"]
    identifier = f["charset_ratios"]["digits"] * f["fixed_length_ratio"] * f["unique_ratio"]
    scores["identifier_lain"] = 82 * identifier if f["max_length"] >= 8 else 0
    if ns["password"]:
        scores["password"] = 90 * sum(bool(re.match(r"^\$(?:argon2id|2[aby])\$", str(v)))
                                     for v in values if v is not None) / max(1, f["nonnull"])
    # A bank elsewhere in the row is weak context. The 16-digit overlap is
    # ambiguous; other fixed numeric identifiers must remain identifiers.
    scores["rekening"] = (85 if bank_context and rx["nik"] > 0.5 else 58) * rx["rekening"]
    if bank_context and rx["nik"] and not ns["nik"]:
        scores["nik"] *= 0.35
        negatives.append("konteks bank melemahkan dugaan NIK")
    if rx["nik"] > f["nik_plausible_ratio"]:
        negatives.append("sebagian digit 16 tidak memenuhi struktur tanggal/wilayah NIK")
    if f["digit_entropy"] < 1.5 and identifier:
        scores["identifier_lain"] *= 0.6
        scores["nik"] *= 0.6
        negatives.append("distribusi digit berulang; bukti identifier lemah")
    for kind in ("agama", "jenis_kelamin", "status_perkawinan", "kesehatan"):
        scores[kind] = 100 * dictionaries[kind]
    scores["tempat_lahir"] = 95 * dictionaries["kota"]
    scores["operasional"] = 100 * dictionaries["bank"]
    if dictionaries["bank"] > 0.5:
        scores["nama"] *= 0.2
    if rx["kode_pos"] > 0.8:
        scores["identifier_lain"] = max(scores["identifier_lain"], 65)
    if ns["nik"] and rx["nik"] < 0.5:
        negatives.append("panjang tidak baku untuk NIK; perlu verifikasi")
    if ns["rekening"] and rx["rekening"] > 0:
        scores["rekening"] = max(scores["rekening"], 95 * rx["rekening"])
        scores["nik"] *= 0.25
        negatives.append("konteks rekening bertentangan dengan label NIK")
    for kind, ratio in f["embedded_ratios"].items():
        scores[kind] = max(scores.get(kind, 0), 82 * ratio)
    if not baseline:
        anonymous_numeric = (f["nonnull"] >= 3 and identifier == 1 and f["max_length"] >= 14
                             and f["max_length"] != 16
                             and not any(ns[k] for k in ("nik", "npwp", "rekening", "telepon")))
        if anonymous_numeric:
            scores["identifier_lain"] = 95
            for ambiguous in ("nik", "npwp", "rekening", "telepon"):
                scores[ambiguous] *= 0.5
            negatives.append("identifier digit unik berpanjang tetap; tanpa konteks jenis perlu review")
        nonstandard_nik = (ns["nik"] and not ns["rekening"] and f["nonnull"] >= 3
                           and f["charset_ratios"]["digits"] == 1 and f["fixed_length_ratio"] == 1
                           and f["unique_ratio"] == 1 and f["max_length"] != 16)
        if nonstandard_nik:
            scores["nik"] = 95
            negatives.append("panjang tidak baku; kandidat NIK didukung digit, panjang tetap, dan keunikan")
        if low_cardinality:
            had_name_evidence = bool(scores["nama"] or ns["nama"] or parts & {"nama", "name"})
            if had_name_evidence:
                scores["kategori"] = max(scores["nama"], scores["operasional"] if parts & {"nama", "name"} else 0,
                                         75 if ns["nama"] else 0)
                ns["kategori"] = 100 if parts & {"nama", "name"} else ns["nama"]
                negatives.append("kardinalitas rendah: bukan kandidat nama orang")
            scores["nama"] = 0
            ns["nama"] = 0
        marriage_date = rx["tanggal"] > 0 and (ns["tanggal_pernikahan"] or
                                              (conditional_presence or {}).get("marital_context"))
        if marriage_date:
            scores["tanggal_pernikahan"] = 95 * rx["tanggal"] if conditional_presence else 90 * rx["tanggal"]
            scores["tanggal_lahir"] = 0
        if family_count:
            scores["keluarga"] = 75
        if surrogate_id:
            scores["operasional"] = 95
            ns["operasional"] = 100
    if baseline:
        scores = {kind: ratio * 100 for kind, ratio in rx.items()
                  if kind in {"email", "telepon", "nik", "npwp", "rekening", "alamat", "tanggal"}}
        if "tanggal" in scores:
            scores["tanggal_lahir"] = scores.pop("tanggal")
        ns = {k: 0 for k in ns}
        negatives = []
    cw = 1 if baseline else config["content_weight"]
    nw = 0 if baseline else config["name_weight"]
    kinds = set(scores) | set(ns)
    kind = max(sorted(kinds), key=lambda k: cw * scores.get(k, 0) + nw * ns.get(k, 0))
    if not baseline and ns["password"]:
        kind = "password"
    if not baseline and family_count:
        kind = "keluarga"
    if not baseline and surrogate_id:
        kind = "operasional"
    content, name = round(scores.get(kind, 0), 2), ns.get(kind, 0)
    confidence = round(cw * content + nw * name, 2)
    conflict = bool(negatives) and (kind == "nik" or content < config["auto_content_threshold"])
    if content >= config["auto_content_threshold"] and confidence >= config["auto_confidence_threshold"] and not conflict:
        triage = "auto_accept"
    elif confidence >= config["review_threshold"] or max(ns.values(), default=0) >= 80 or negatives:
        triage = "needs_review"
    else:
        triage = "low_confidence"
    internal_kind = kind
    if not baseline and (family_count or anonymous_numeric or (kind == "identifier_lain" and not ns["identifier_lain"])):
        triage = "needs_review"
    if confidence < 20 and max(ns.values(), default=0) == 0:
        kind = "kategori" if f["unique_ratio"] < 0.2 and f["nonnull"] else "tidak_diketahui"
    if kind == "jenis_kelamin":
        kind = "kategori"
    if kind in {"kesehatan", "biometrik", "genetika", "kejahatan", "password"}:
        kind = "identifier_lain"
    sensitive_context = any(ns[k] for k in ("kesehatan", "biometrik", "genetika", "kejahatan"))
    specific = (internal_kind in {"rekening", "kesehatan", "biometrik", "genetika", "kejahatan"}
                or sensitive_context
                or bool(not family_count and ns["keluarga"] and any(w in column.lower() for w in ("anak", "child"))))
    # A generic shape winning over a sensitive field name is a conflict to
    # review, not a reason to downgrade the proposed legal protection class.
    if sensitive_context and internal_kind not in {"kesehatan", "biometrik", "genetika", "kejahatan"}:
        triage = "needs_review"
        negatives.append("konteks data spesifik membutuhkan verifikasi manusia")
    pdp = "spesifik" if specific else "non_pribadi" if kind == "operasional" and content >= 70 else "umum"
    institution_reference = (not baseline and kind == "kategori" and low_cardinality
                             and max(dictionaries["bank"], dictionaries["government_office"]) >= 0.8)
    if institution_reference:
        pdp = "non_pribadi"
    if family_count and not baseline:
        pdp = "umum"
    factor_kind = internal_kind if internal_kind in {"kesehatan", "biometrik", "genetika", "kejahatan", "password"} else kind
    if sensitive_context:
        factor_kind = next(k for k in ("kesehatan", "biometrik", "genetika", "kejahatan") if ns[k])
    factors = priority_factors(factor_kind, content, f["unique_ratio"], environment,
                               config.get("type_policy") or load_type_policy())
    priority_score = sum(factors.values())
    priority = rank(priority_score)
    risk = {"P0": "kritis", "P1": "tinggi", "P2": "sedang", "P3": "rendah"}[priority]
    decision = config.get("retention", {}).get(column, "review")
    if password_column or internal_kind == "password":
        recommendation = "hash"
    elif decision == "delete":
        recommendation = "delete"
    elif pdp == "non_pribadi":
        recommendation = "retain"
    elif kind == "nama":
        recommendation = "retain+mask_for_analyst"
    elif kind == "tanggal_lahir":
        recommendation = "generalize_for_analyst"
    elif internal_kind in {"nik", "rekening", "npwp", "identifier_lain"}:
        recommendation = "encrypt+blind_index+mask"
    else:
        recommendation = "encrypt+mask"
    reasons = ["perlu disimpan? " + ("tinjau kebutuhan retensi" if decision == "review" else decision),
               f"{f['digit_ratio']:.0%} digit", f"panjang {f['min_length']}-{f['max_length']}",
               f"panjang tetap {f['fixed_length_ratio']:.0%}", f"rasio unik {f['unique_ratio']:.0%}",
               f"NULL {f['null_ratio']:.0%}", f"bukti isi {content:.1f}; nama {name}"]
    if name:
        reasons.append("kamus nama: " + ", ".join(w for w in NAMES.get(internal_kind, ()) if w in column.lower()))
    other_name_hits = [k for k, score in ns.items() if score and k != internal_kind]
    if other_name_hits:
        reasons.append("sinyal nama tambahan: " + ", ".join(other_name_hits))
    reasons += negatives
    if not baseline and low_cardinality and internal_kind == "kategori":
        reasons.append(f"{f['unique_count']} nilai unik; kategori, bukan nama orang")
    if institution_reference:
        reasons.append("bukti isi referensi institusi; asosiasi dengan individu tetap memerlukan kontrol akses")
    if not baseline and family_count:
        reasons.append("bilangan hitungan keluarga; bukan data anak individual")
    if not baseline and surrogate_id:
        reasons.append("kunci penghubung; integer berurutan unik pada sampel, kandidat surrogate PK")
    if not baseline and internal_kind == "tanggal_pernikahan":
        reasons.append("pola tanggal dan konteks pernikahan")
        if conditional_presence:
            reasons.append("pola NULL bersyarat pada " + ", ".join(conditional_presence["source_columns"]))
    if kind == "nama":
        reasons.append("nama berentropi rendah/publik; hash rentan kamus, batasi tampilan analis")
    if password_column or internal_kind == "password":
        reasons.append("password wajib hash Argon2id")
    if internal_kind == "agama":
        reasons.append("rawan diskriminasi; UU PDP Pasal 4(3): umum")
    f.update({"name_scores": ns, "type_content_scores": scores, "negative_evidence": negatives,
              "semantic_candidate": internal_kind,
              "family_count": family_count, "surrogate_id_candidate": surrogate_id,
              "institution_reference": institution_reference,
              "conditional_presence": conditional_presence or {},
              "sensitivity_note": "rawan diskriminasi" if internal_kind == "agama" else ""})
    examples = list(dict.fromkeys(str(v) for v in values if v is not None and str(v).strip()))[:3]
    # Free text samples are summarized; only a whole-value match uses a specific mask.
    samples = [mask(v, kind if kind not in PATTERNS or PATTERNS[kind].fullmatch(v) else "tidak_diketahui") for v in examples]
    result = {"detected_type": kind, "pdp_class": pdp, "risk_level": risk, "priority": priority,
              "priority_score": priority_score, "content_score": content, "name_score": name,
              "confidence": confidence, "triage": triage, "derived_from": "", "consistent_protection_with": "",
              "sample_masked": " | ".join(samples), "reason": "; ".join(reasons),
              "recommendation": recommendation, "allowed_roles": ",".join(config["allowed_roles"]),
              "search_need": config["search_need"]}
    result.update({"f_" + k: v for k, v in factors.items()})
    return result, f
