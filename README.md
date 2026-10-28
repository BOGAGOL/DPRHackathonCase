# Pelindungan Data Pribadi ketika Database Bocor

Prototipe Tim BOGAGOL untuk Final Hackathon DPR RI 2026. Aplikasi aktif berada di
`app/`, memakai PostgreSQL **18** di `pg-dpr:5433` dan OpenBao **2.5.5** dengan TLS.
Format data, enkripsi dan kewenangan mengikuti [kontrak teknis](docs/contracts/CONTRACT.md).

## Panduan aktif

| Kebutuhan | Panduan |
|---|---|
| Instalasi PostgreSQL/OpenBao pada VM baru | [Fresh VM](infra/vm/README.md) |
| Aplikasi backend/frontend | [Service App](app/README.md) |
| Scanner dan inventaris | [Scanner](scanner/README.md) |
| Migrasi ke database baru | [Migrasi](migration/README.md) |
| Backup/restore terenkripsi | [Backup](scripts/backup/README.md) |
| Rotasi kunci | [Rotasi](infra/rotation/README.md) |
| Upgrade analis A5 pada server existing | [A5](infra/protected/ANALYST_SUPPRESSION.md) |
| Uji browser dan pemulihan nyata | [Acceptance](infra/acceptance/README.md) |
| Kesiapan pengumpulan dan scope bukti | [Readiness](docs/SUBMISSION_READINESS.md) |

## Struktur

```text
app/             Satu aplikasi aktif: Next.js, FastAPI, enam peran
infra/           PostgreSQL 18, OpenBao TLS, acceptance dan operasi
scanner/         Inventaris, klasifikasi dan evaluasi deteksi
policy/          Keputusan per kolom dan protection profile
migration/       Migrasi resumable dan decrypt-and-compare
sql/             Skema dan role minimum
toolkit/         Paket Python dprcrypto
scripts/backup/  Backup streaming, restore, tamper dan retensi
datagen/         Pembesaran data sintetis
benchmark/       Pengukuran kinerja; baseline awal pada snapshot ini
verify/          Verifikasi dan konfigurasi cakupan
docs/            Kontrak, panduan dan dokumentasi lomba
evidence/        Hasil mesin tanpa rahasia/data pribadi
archive/         Dokumen/evidence prototipe lama, bukan acuan runtime
```

Runtime PostgreSQL 17 (`apps/`, `infrastructure/`, compose dan skrip lama) sudah
retired; versi sebelumnya tersedia di riwayat Git. Lihat [arsip](archive/README.md).
Tidak ada perubahan format enkripsi, isi database, kunci atau target benchmark
sebagai bagian dari perapian struktur ini.

## Lingkungan dan test

Python **3.11+**, Node.js yang mendukung Next.js proyek, Docker/Compose V2 untuk
container dan Chrome untuk acceptance browser. Dari root repo:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r infra/requirements.txt
.venv/Scripts/python -m pip install -r app/requirements.txt
.venv/Scripts/python -m pip install -e toolkit
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m pytest -c app/pytest.ini app/tests -q
```

Default pytest menjalankan suite A. Jalankan B dan setiap modul C sebagai proses
terpisah agar conftest/import tetap terisolasi. Scanner/datagen/benchmark mempunyai
requirements tersendiri; gunakan environment modul untuk mencocokkan pin versinya.
Untuk frontend: `cd app/web`, `npm ci`, lalu `npm run build`.

Ikuti runbook fresh VM hanya untuk stack baru. Pada server existing jangan mengulang
init, import atau prepare/provision untuk sekadar memperbarui aplikasi. Service App
membaca environment eksplisit; contoh di [app/.env.example](app/.env.example).

## Status bukti dan kerahasiaan

Acceptance setelah A5 mencatat 143 pemeriksaan pada lab PG18/OpenBao TLS berisi
17 record buatan sendiri serta 100 pemeriksaan pada deployment melalui enam akun.
Lihat [ringkasan](evidence/acceptance/post-a5-summary.json). Ini tidak menggantikan
benchmark resmi, pengujian seluruh dataset atau inspeksi internal VM lewat SSH.

Repo tetap PRIVATE. Dataset panitia bukan bahan publik. Rahasia, file akun demo,
kunci, token, dump dan material pemulihan disimpan di luar checkout, tidak ikut Git
atau paket pengumpulan. Kode mengikuti [MIT](LICENSE); lisensi dokumentasi dan
atribusi pihak ketiga akan dirinci pada paket dokumentasi pengumpulan.
