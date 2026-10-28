# Reproduksi dan pengujian

Jalankan dari root repo dengan Python 3.11+. Environment modul disarankan karena
pin A/B dan C berbeda. Contoh Windows; pada Linux gunakan `bin/python`.

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r infra/requirements.txt -r app/requirements.txt -r infra/submission/requirements.txt
.venv/Scripts/python -m pip install -e toolkit
Push-Location app/web
npm ci
npm run build
Pop-Location
```

## Unit/regresi tanpa database tim

```powershell
# Core A: integrasi eksternal default skip.
.venv/Scripts/python -m pytest -q
# Backend B: SQLite/invented fixtures; bukan bukti live PG/Bao.
.venv/Scripts/python -m pytest -c app/pytest.ini app/tests -q
# Jalankan C sebagai proses terpisah; install requirements modul bersangkutan.
python -m pytest scanner/tests -q --import-mode=importlib
python -m pytest datagen/tests -q --import-mode=importlib
python -m pytest benchmark/tests verify/tests -q --import-mode=importlib
# Frontend synthetic UI; scope berbeda dari live Chrome.
Push-Location app/web
npm run test:ui
Pop-Location
```

Jangan menghitung test skip sebagai lulus. Benchmark unit dapat membaca syarat AC
laptop; bila test bergantung hardware, catat kendalanya dan mock sensor pada unit
tanpa mematikan guard benchmark nyata. Jangan menjalankan benchmark/migrasi secara
tidak sengaja melalui perintah pengujian; integrasi live memerlukan opt-in jelas.

## Integrasi nyata terisolasi

- [Acceptance setelah A5](../../infra/acceptance/README.md): PG18/OpenBao TLS,
  backup/restore tujuh tabel, aplikasi dan Chrome nyata; 17 record buatan sendiri.
- [TLS pg-dpr](../../infra/postgres/README.md): inspect/apply/verify pada instance
  yang dipilih operator. Membaca panduan tidak berarti boleh menerapkan ke laptop benchmark.
- [VM fresh](../../infra/vm/README.md): hanya stack baru, input dan rahasia privat.
- [Rilis A5](../../app/docs/DEPLOY_A5.md): server existing, upgrade spesifik saat maintenance.

## Data, migrasi dan backup

Panitia menyediakan input 734 record lewat penyimpanan privat; paket publik tidak
memuat `02_data.sql`. `01_schema.sql`/`03_validasi.sql` dan [README baseline](../../sql/baseline/README.md)
menjelaskan input. Jangan memasukkan 734 record ke fixture test baru.

[Datagen](../../datagen/README.md) memakai seed 42 untuk baseline_100k/1m. Source
dan baseline immutable sesuai runbook; target protected adalah database baru.
[Migrasi](../../migration/README.md) memeriksa resume/idempotensi/decrypt-and-compare.
Jangan menjalankan prepare ulang pada Service App aktif untuk mengganti kode.

[Backup](../../scripts/backup/README.md) menulis artefak terenkripsi di luar repo,
restore selalu ke DB baru. [Cutover recovery](../../app/docs/RECOVERY.md) menjaga
nama/marker target, role, RLS, TLS dan pemulihan aplikasi. Untuk timing resmi, ulang
minimal tiga kali dengan hardware/dataset/workload yang sebanding dan catat raw.

## Verifikasi bahan pengumpulan

```powershell
python -m infra.submission sbom
python -m infra.submission check
python -m infra.submission build --output dist/submission
```

Cek file `SOURCE_MANIFEST.json` dan `QUALITY_REPORT.json` di ZIP. Jalankan ulang
test yang relevan dari paket bersih; tidak membutuhkan checkout arsip/reference
atau credential lama. Database live/OpenBao/pemilik benchmark tetap prasyarat
terpisah, bukan sesuatu yang dibuat otomatis oleh check/build.
