from datetime import date, timedelta

import pytest

from datagen.model import COLUMNS


@pytest.fixture
def source():
    """Handmade synthetic data; no organizer values or copied dump rows."""
    result = []
    for i in range(1, 41):
        born = date(1970 + i % 30, 1, 1)
        married = None if i % 2 == 0 else born + timedelta(days=(-90 if i % 7 == 0 else 1000 if i % 3 == 0 else 8000))
        name = "FixtureLetters" + chr(65 + i % 26) * 12 + str(i)
        row = dict.fromkeys(COLUMNS)
        row.update(id=i, nama=name, nama_lengkap=name, nama_tanpa_gelar=name,
                   jenis_kelamin="L" if i % 3 else "P", tempat_lahir=f"KotaSintetis{i % 4}",
                   tanggal_lahir=born, tanggal_pernikahan=married, no_ktp=f"0{i:013d}",
                   pekerjaan_terakhir=f"PekerjaanUji{i % 5}", alamat_jakarta=f"Jl. Fixture No. {i}, Jakarta",
                   telpon_jakarta=f"021{i:08d}", alamat_daerah=f"Jl. Fixture No. {i}, KotaSintetis{i % 4}",
                   telpon_daerah=f"0{i:09d}", handphone=f"081{i:07d}", email=f"fixture{i}@example.test",
                   ruangan=f"DUMMY-{i:03d}", status_kawin="K" if married else "TK", jumlah_anak=i % 4,
                   jumlah_tanggungan=i % 4 + int(married is not None),
                   jumlah_jiwa=i % 4 + int(married is not None) + 1,
                   rekening=f"0{i:015d}", nama_rekening=name[:20], npwp=f"0{i:014d}",
                   nama_kppn=f"KantorUji{i % 3}", nip_kppn=f"0{i:017d}", nama_bank=f"BankUji{i % 2}",
                   kode_bank=str(i % 7).zfill(3), pengguna=f"fixture_{i}", agama=f"KategoriUji{i % 3}")
        result.append(row)
    return result
