# Penerapan A5: analis hanya menerima agregat

SQL kanonis: `sql/protected/03_analyst_suppression.sql`. Interface:
`public.analyst_summary(dimension text, value text, anggota_count bigint)`;
lima marginal terpisah, masing-masing `HAVING count(*) >= 5`. Label kelompok kecil
tidak dikembalikan. Fungsi lama `analyst_age_summary()` juga tunduk pada ambang ini.
Rincian DTO/filter/total untuk Modul B ada di CONTRACT bagian 10.1.

## Server yang sudah berisi protected_734

1. Koordinasikan maintenance `/analytics/summary` dan rilis query Modul B terlebih dahulu.
   `analytics.py` lama akan mendapat permission denied setelah upgrade; endpoint lain
   tidak memerlukan perubahan kripto. Pull kode saja tidak mengubah database.
2. Jalankan dari checkout server `~/juara1onno` dengan virtualenv dependensi proyek.
   Muat kredensial administrator dan CA dari penyimpanan privat yang sudah ada.
   Contoh Bash untuk paket VM Modul A (jangan aktifkan shell tracing `set -x`):

   ```bash
   cd ~/juara1onno
   git pull --ff-only origin main
   export DPR_SECRETS_DIR="$HOME/dpr-demo-zhafif/private/module-a"
   set -a
   . "$DPR_SECRETS_DIR/operator.env"
   set +a
   .venv/bin/python -m infra.protected.analyst --database protected_734
   .venv/bin/python -m infra.protected.analyst --database protected_734 --verify-only
   ```

   Sesuaikan path ke `operator.env` yang benar; jangan membuat kredensial pengganti.
   CLI memakai PGHOST/PGPORT/PGUSER/PGPASSWORD/PGSSLROOTCERT dari env,
   wajib TLS `verify-full`. Password tidak masuk argumen proses. Di PowerShell,
   setelah environment kredensial existing dimuat, gunakan
   `.venv\Scripts\python.exe -m infra.protected.analyst --database protected_734`.
3. Pastikan kedua hasil `passed: true`. Laporan metadata tanpa nilai anggota disimpan
   di `evidence/access-control/analyst-upgrade.json`; gunakan `--evidence <path>` berbeda
   bila ingin menyimpan apply dan verify terpisah. SQL berjalan dalam satu transaksi,
   lock timeout 5 detik, statement timeout 60 detik; kegagalan me-rollback seluruh upgrade.
4. Aktifkan query Modul B baru, uji enam akun dan endpoint analytics. Kirim JSON hasil
   apply/verify serta hasil test Modul B untuk validasi; jangan kirim rahasia atau baris anggota.

**Jangan menjalankan full `infra.protected.apply`/migration prepare pada DB aplikasi aktif
untuk A5:** provisioning penuh dapat mengembalikan LOGIN migration_user dan mereset grant
tabel milik Modul B. CLI A5 hanya mengubah interface/ACL analis, tanpa perubahan password,
LOGIN role, data anggota, assignment akun, sesi, atau sequence. Tidak membutuhkan OpenBao.
Skema baru otomatis menyertakan SQL A5 melalui provisioning biasa.

Tidak ada penerapan ke laptop Delf dari pekerjaan ini. Untuk protected_100k/protected_1m,
pemilik benchmark baru menjalankan upgrade setelah sesi benchmark dihentikan dan disepakati.
CLI menolak postgres/baseline_*, PostgreSQL selain 18, role analyst berbahaya/membership,
dan pemilik tabel yang tidak sesuai. Tidak ada perubahan konfigurasi TLS/pg_hba.

## Restore dan rollback

Restore backup terautentikasi lama/baru menjalankan SQL A5 sebelum membuka CONNECT runtime;
ACL yang dulu mengizinkan view per record tidak diaktifkan kembali. Jumlah baris pada manifest
tetap diverifikasi. Untuk backup Service App, query analytics hasil restore juga harus memakai
kontrak baru; startup/recovery kode B yang lama tidak membuat query lama menjadi kompatibel.

Jika SQL gagal, transaksi dibatalkan dan akses tidak berubah. Jika aplikasi B belum siap,
pertahankan maintenance endpoint analytics; jangan memberikan kembali SELECT per record.
Mengulang CLI A5 aman dan tidak mengubah data. Tidak perlu migrasi ulang atau enkripsi ulang.

CONTRACT diperbarui atas instruksi tim untuk perubahan ACL, dengan protection_version tetap 1.
Profile dibangun ulang hanya untuk memperbarui hash provenance CONTRACT; keputusan kripto
per kolom tetap sama. Jangan menggunakan profile baru untuk resume checkpoint migrasi lama
yang hash profilenya berbeda; selesaikan migrasi dengan checkout/profile asal. Untuk database
yang sudah selesai migrasi, gunakan hanya CLI A5 di atas.

## Reproduksi pengujian sintetis

Docker yang sehat, container PostgreSQL 18 sementara dengan port acak:

```powershell
$env:DPR_ANALYST_INTEGRATION = '1'
.venv\Scripts\python.exe -m pytest infra/tests/test_analyst_suppression_integration.py -q
```

Alternatif bila Docker Desktop bermasalah: set `DPR_NATIVE_PG_BIN` ke direktori binary
PostgreSQL 18 (`initdb`, `pg_ctl`, `psql`, `postgres`), lalu jalankan test yang sama.
Test membuat cluster terisolasi dalam folder temporer di luar Git, hanya bind loopback
dengan port acak dan password sintetis SCRAM, tidak memasang Windows service atau menyentuh
cluster lain. PostgreSQL 17 ditolak. Native dan Docker sama-sama menjalankan SQL provisioning
produksi; jalur native menggantikan transport `docker exec` dengan `psql` lokal.

Evidence `evidence/access-control/analyst_suppression.json` menyebut transport, versi,
scope sintetis, denial SQLSTATE 42501, ambang 1–4/5–6/NULL, idempotensi dan restore ACL lama.
Ini bukti kontrol DB, bukan bukti endpoint Modul B sudah diperbarui.
