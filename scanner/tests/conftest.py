from pathlib import Path

import pytest
import yaml

from scanner.model import Table
from scanner.priority import load_type_policy


@pytest.fixture
def config():
    path = Path(__file__).parents[1] / "config" / "weights.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    value["type_policy"] = load_type_policy()
    return value


@pytest.fixture
def environment():
    return {"volume": 3, "exposure": 5, "recovery": 5}


@pytest.fixture
def synthetic():
    """Invented here; no competition dump values are used."""
    columns = ["nama", "nama_lengkap", "nama_tanpa_gelar", "nama_rekening", "pengguna", "email",
               "handphone", "no_ktp", "rekening", "tanggal_lahir", "alamat_daerah", "tempat_lahir",
               "jenis_kelamin", "agama", "status_kawin", "tanggal_pernikahan", "jumlah_tanggungan",
               "jumlah_jiwa", "nama_bank", "nik"]
    first = ["Zafira", "Nayaka", "Taluna", "Ravika", "Miranta", "Samira"]
    last = ["Arunika", "Bimantara", "Cakrawala", "Dewantara"]
    cities = ["Jakarta", "Bandung", "Surabaya", "Semarang", "Medan", "Makassar"]
    rows = []
    for index in range(24):
        name = first[index % 6] + " " + last[index // 6]
        city = cities[index % 6]
        rows.append((name, name, name, first[index % 6], name.replace(" ", "").lower() + str(index),
                     name.replace(" ", ".").lower() + str(index) + "@fixture.example",
                     "08123456" + f"{9700 + index:04d}", "4783921056" + f"{9700 + index:04d}",
                     "317401010190" + f"{9700 + index:04d}", f"1988-06-{index + 1:02d}",
                     f"Jl. Rekaan No. {index + 11}, Kel. Imajinasi, {city}", city,
                     "L" if index % 2 else "P", "Islam" if index % 3 else "Hindu",
                     "K" if index % 2 else "BK", f"2015-08-{index + 1:02d}" if index % 2 else None,
                     index % 5, index % 5 + 1, "BCA", f"317401{index + 1:02d}0690{9700 + index:04d}"))
    return Table("public.fixture", columns, ["text"] * len(columns), rows, len(rows))


@pytest.fixture
def sql_dump(synthetic, tmp_path):
    path = tmp_path / "fixture.sql"
    def literal(value):
        return "NULL" if value is None else "'" + str(value).replace("'", "''") + "'"
    columns = ", ".join('"' + col + '" TEXT' for col in synthetic.columns)
    inserts = ",\n".join("(" + ",".join(literal(v) for v in row) + ")" for row in synthetic.rows)
    path.write_text(f"CREATE TABLE public.fixture ({columns});\nINSERT INTO public.fixture VALUES\n{inserts};\n", encoding="utf-8")
    return path
