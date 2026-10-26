"""The only boundary for sample values leaving the scanner."""
import re
import unicodedata


def normalize(value):
    text = unicodedata.normalize("NFKD", str(value)).lower()
    if any(c.isalpha() for c in text):
        text = re.sub(r"\d+\s*$", "", text)
    return re.sub(r"[^a-z0-9]", "", text)


def mask(value, kind="tidak_diketahui"):
    text = str(value).strip()
    if not text:
        return "<kosong>"
    if kind == "email" and "@" in text and not re.search(r"\s", text):
        local, domain = text.rsplit("@", 1)
        if re.fullmatch(r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}", domain):
            return local[:min(2, max(0, len(local) - 1))] + "***@" + domain
    if kind == "nama" and re.fullmatch(r"[^\W\d_]+(?:[ .'-]+[^\W\d_]+)*", text):
        return " ".join(w[:min(2, max(0, len(w) - 1))] + "***" for w in text.split())
    digits = re.sub(r"\D", "", text)
    if kind in {"nik", "telepon"} and len(digits) > 8:
        return digits[:4] + "*" * (len(digits) - 8) + digits[-4:]
    if kind in {"rekening", "npwp"} and len(digits) > 4:
        return "*" * (len(digits) - 4) + digits[-4:]
    char_type = "digit" if text.isdecimal() else "huruf" if text.isalpha() else "campuran"
    return f"<{len(text)} {char_type}>"
