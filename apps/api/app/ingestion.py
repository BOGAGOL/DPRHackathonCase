"""Non-executing parser for the supplied one-row MySQL INSERT grammar."""
import re
from pathlib import Path

from sqlalchemy import JSON, Column, Integer, MetaData, Table, select
from sqlalchemy.orm import Session

from .models import ImportRun, Member

COLUMNS = "nama nama_lengkap nama_tanpa_gelar jenis_kelamin tempat_lahir tanggal_lahir tanggal_pernikahan no_ktp pekerjaan_terakhir alamat_jakarta telpon_jakarta alamat_daerah telpon_daerah handphone email ruangan status_kawin jumlah_anak jumlah_tanggungan jumlah_jiwa rekening nama_rekening npwp nama_kppn nip_kppn nama_bank kode_bank pengguna agama".split()
PUBLIC = {"nama", "ruangan"}
SENSITIVE = set(COLUMNS) - PUBLIC
INSERT = re.compile(r"INSERT\s+INTO\s+`anggota`\s*\(([^)]+)\)\s+VALUES\s*\((.*)\);", re.I)
TOKEN = re.compile(r"\s*(?:'((?:[^'\\]|\\.|'')*)'|(NULL|[-+]?\d+(?:\.\d+)?))\s*(,|$)", re.I)
ESCAPES = {"0": "\x00", "n": "\n", "r": "\r", "t": "\t", "b": "\b", "Z": "\x1a"}


def parse_values(raw):
    values, pos = [], 0
    while pos < len(raw):
        match = TOKEN.match(raw, pos)
        if not match or match.end() == pos:
            raise ValueError("Unsupported SQL value grammar")
        if match.group(2) and match.group(2).upper() == "NULL":
            value = None
        elif match.group(2):
            value = match.group(2)
        else:
            value = re.sub(r"\\(.)", lambda m: ESCAPES.get(m[1], m[1]), match[1]).replace("''", "'")
        values.append(value)
        pos = match.end()
        if not match[3]:
            break
        if pos == len(raw):
            raise ValueError("Trailing comma")
    if pos != len(raw):
        raise ValueError("Unsupported SQL suffix")
    return values


def load_rows(path: Path, expected_count=734):
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        match = INSERT.fullmatch(line.strip())
        if not match or re.findall(r"`([^`]+)`", match[1]) != COLUMNS:
            raise ValueError(f"Unsupported SQL or source columns at line {number}")
        values = parse_values(match[2])
        if len(values) != 29:
            raise ValueError(f"Invalid column count at line {number}")
        rows.append(dict(zip(COLUMNS, values)))
    if len(rows) != expected_count:
        raise ValueError(f"Expected {expected_count} records; received {len(rows)}")
    return rows


baseline_metadata = MetaData()
baseline_members = Table("baseline_members", baseline_metadata,
                         Column("id", Integer, primary_key=True, autoincrement=False), Column("source", JSON, nullable=False))


def import_baseline(engine, rows):
    baseline_metadata.create_all(engine)
    with engine.begin() as connection:
        existing = connection.execute(select(baseline_members)).all()
        if existing:
            if {r.id: r.source for r in existing} != dict(enumerate(rows, 1)):
                raise ValueError("Baseline differs; refusing to overwrite")
        else:
            connection.execute(baseline_members.insert(), [{"id": i, "source": r} for i, r in enumerate(rows, 1)])


def protect_rows(session: Session, protection, rows, source_sha256):
    existing_run = session.scalar(select(ImportRun).where(ImportRun.source_sha256 == source_sha256))
    if existing_run:
        verify_rows(session, protection, rows)
        return False
    if session.scalar(select(Member.id).limit(1)) is not None:
        raise ValueError("Non-empty protected database; refusing to overwrite")
    for i, row in enumerate(rows, 1):
        session.add(Member(id=i, nama=row["nama"], ruangan=row["ruangan"],
                           ktp_index=protection.blind_index(row["no_ktp"]) if row["no_ktp"] is not None else None,
                           protected_fields={f: protection.encrypt(i, f, row[f]) for f in sorted(SENSITIVE)}))
    session.flush()
    verify_rows(session, protection, rows)
    session.add(ImportRun(source_sha256=source_sha256, record_count=len(rows), column_count=29))
    session.commit()
    return True


def verify_rows(session, protection, rows):
    members = session.scalars(select(Member).order_by(Member.id)).all()
    if len(members) != len(rows):
        raise ValueError("Record count mismatch")
    for i, (member, row) in enumerate(zip(members, rows), 1):
        actual = {"nama": member.nama, "ruangan": member.ruangan}
        if set(member.protected_fields) != SENSITIVE or member.id != i:
            raise ValueError("Record identity or field mismatch")
        actual.update({f: protection.decrypt(member.id, f, member.protected_fields[f]) for f in SENSITIVE})
        if actual != row:
            raise ValueError("Logical equality failed (values withheld)")
        expected = protection.blind_index(row["no_ktp"]) if row["no_ktp"] is not None else None
        if member.ktp_index != expected:
            raise ValueError("Blind index mismatch")
    return {"records": len(rows), "columns": 29, "logical_equality": True, "blind_index": True}
