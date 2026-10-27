# PostgreSQL proyek: pg-dpr:5433, TLS tanpa recreate

Allowlist migrasi kini juga mencakup baseline_1m/protected_1m. Jalankan kembali
enable_tls apply setelah menarik pembaruan agar blok HBA lama tiga database
ditingkatkan ke lima database tanpa recreate/restart; aturan auth lain dan source
postgres dipertahankan. Database 1M tidak otomatis dibuat oleh pembaruan TLS.
Target dibuat oleh python -m migration prepare --target protected_1m; gunakan
baseline_1m yang telah dibuat/diterima C dan panduan migration/README.md.

Keputusan tim 27 Oktober 2026: PostgreSQL **18** yang sudah ada di `pg-dpr`, port
host **5433**, menampung `baseline_100k`, `protected_734`, `protected_100k`.
OpenBao memakai `infra/compose.yaml`, TLS port 8200. Database asli `postgres`
tetap sumber read-only. File acuan mesin: `infra/database-targets.json`.

## Laptop Alby: clone development lokal

Klarifikasi pengguna: instance resmi/benchmark berada di laptop anggota tim
lain. Laptop ini mempunyai clone development sendiri. Baseline dan pengukuran
resmi tetap di laptop tersebut; jangan mengganti evidence resmi dengan hasil
development. Path repo laptop ini berbeda dari C:\dev pada contoh teman:
`C:\Users\Muhammad Albyarto Gh\Documents\Onno\juara1onno`.

Container lokal **sudah dibuat**, source 734 dan baseline 100k sudah diimport,
TLS sudah aktif. Perintah berikut hanya untuk reproduksi pada laptop kosong;
create/import/baseline menolak overwrite instance/data yang sudah ada:

```powershell
$env:DPR_SECRETS_DIR = Join-Path $env:LOCALAPPDATA 'DPR\crypto-infra-tls'
.\.venv\Scripts\python.exe -m infra.postgres.development create
# CA OpenBao sudah ada; bila belum, buat sekali: python -m infra.tls.make_ca
.\.venv\Scripts\python.exe -m infra.postgres.make_cert
.\.venv\Scripts\python.exe -m infra.postgres.enable_tls apply
# Letakkan SQL privat panitia di sql/baseline/02_data.sql (gitignored).
.\.venv\Scripts\python.exe -m infra.postgres.development import-source
.\.venv\Scripts\python.exe -m infra.postgres.development empty-targets
.\.venv\Scripts\python.exe -m infra.postgres.development baseline
```

Bootstrap memakai volume bernama `pg-dpr-data` di parent PG18
`/var/lib/postgresql`, publish loopback 5433, password CSPRNG via env Docker
(tanpa nilai password dalam argumen). Credential disimpan sebagai PSCredential
XML terenkripsi Windows DPAPI, ACL operator saja, di direktori eksternal
`postgres/admin.credential.xml`. Credential ini terikat akun/mesin Windows saat
dibuat. CA dan password/key privat tetap lokal; jangan kirim ke chat/repo.

Untuk sesi administrasi lokal yang memerlukan env libpq (tidak menampilkan password):

```powershell
$credential = Import-Clixml -LiteralPath (Join-Path $env:DPR_SECRETS_DIR 'postgres\admin.credential.xml')
$env:PGUSER = $credential.UserName
$env:PGPASSWORD = $credential.GetNetworkCredential().Password
$env:PGHOST = '127.0.0.1'
$env:PGPORT = '5433'
$env:PGSSLMODE = 'verify-full'
$env:PGSSLROOTCERT = Join-Path $env:DPR_SECRETS_DIR 'postgres\tls\ca.crt'
$credential = $null
# ... administrasi lokal ...
# Sesudah sesi: Remove-Item Env:PGPASSWORD
```

Token/OpenBao dan credential DB tidak saling dipakai. Akun postgres ini bukan
akun Service App; role aplikasi akan diprovision pada tahap skema/role.

Import mem-parsing literal INSERT di RAM dengan lexer scanner, bukan menjalankan
dump SQL secara bebas atau menyalin plaintext dump ke /tmp container. Hanya
kolom/tabel anggota yang sesuai diterima, INSERT ke DB memakai bind parameters,
dan tabel sumber yang sudah ada ditolak. Setelah initial population, sumber
hanya dibaca. Baseline memakai generator Modul C, rows=100000, seed=42, serta
validasi identik; writer evidence diarahkan sementara ke `evidence/development/`
dan dipulihkan setelah operasi. Tidak mengubah file/kode Modul C atau laporan
resmi di `evidence/datasets/baseline_100k.json`.

Untuk pekerjaan harian, gunakan verifikasi read-only:

```powershell
$env:DPR_SECRETS_DIR = Join-Path $env:LOCALAPPDATA 'DPR\crypto-infra-tls'
.\.venv\Scripts\python.exe -m infra.postgres.development verify
.\.venv\Scripts\python.exe -m infra.postgres.enable_tls verify
```

Verifier memeriksa TLS SQL pada empat DB dan menghitung ulang checksum source +
baseline dengan streaming cursor/read-only transaction. protected_734 dan
protected_100k saat ini **database kosong**, belum skema/hasil migrasi terproteksi.
Role aplikasi/GRANT akan dipasang pada tahap berikutnya; akun postgres di sini
hanya bootstrap lokal, bukan credential untuk Service App.

Container/laptop resmi teman harus menerapkan skrip TLS pada instance miliknya
sendiri dan mendistribusikan CA publik yang sesuai. Penerapan lokal ini tidak
berarti TLS server laptop lain ikut berubah.

## Aktifkan pada instance yang benar

Jalankan dari root repo di komputer/context yang benar-benar memiliki `pg-dpr`.
Skrip menolak container hilang, bukan PG18, port berbeda, data tanpa persistent
mount, setting SSL dari command line, atau setting yang perlu restart. Tidak ada
perintah create/recreate/restart/delete container/volume dalam skrip TLS.

```powershell
.\.venv\Scripts\python.exe -m pip install -r infra/requirements.txt
$env:DPR_SECRETS_DIR = Join-Path $env:LOCALAPPDATA 'DPR\crypto-infra-tls'
# Opsional: context Docker yang memang memiliki pg-dpr.
# $env:DPR_DOCKER_CONTEXT = 'nama-context'
docker start pg-dpr
.\.venv\Scripts\python.exe -m infra.postgres.enable_tls inspect
```

Jika material CA OpenBao belum ada, buat sekali memakai `python -m
infra.tls.make_ca`. Leaf PostgreSQL berbeda dari leaf OpenBao dan ditandatangani
CA lokal yang sama. CA signing key tidak disalin ke container.

```powershell
# Sekali saja; generator menolak overwrite. Tambahkan SAN bila host DB remote.
.\.venv\Scripts\python.exe -m infra.postgres.make_cert
# Contoh host remote: ... make_cert --dns-name db.example.test --ip-address 192.0.2.10
.\.venv\Scripts\python.exe -m infra.postgres.enable_tls apply
if ($LASTEXITCODE -ne 0) { throw 'TLS belum berhasil diterapkan; periksa evidence/status rollback.' }
.\.venv\Scripts\python.exe -m infra.postgres.enable_tls verify
```

Untuk Docker context remote, set PGHOST ke host database yang dapat dijangkau dari
komputer pemanggil (bukan 127.0.0.1 komputer yang berbeda). Sertifikat harus punya
SAN host/IP itu; port tetap 5433. Context dipakai untuk Docker exec/cp, PGHOST
dipakai untuk verifikasi jaringan. User admin diambil dari env
`DPR_POSTGRES_ADMIN_USER` atau POSTGRES_USER container; administrasi psql lewat
Unix socket `template1`, bukan tabel/database sumber. Skrip mengasumsikan image
Linux PostgreSQL resmi dengan OS user postgres dan socket admin yang dapat
diakses. Tidak mengambil/mencetak password admin dari isi data/database.

Alur apply:

1. Validasi PG18, mount persisten, port, hak admin, dan parameter reloadable.
2. Simpan konfigurasi/HBA asli dan setting SSL sebelumnya ke folder eksternal
   `postgres/changes/<id>/`. Folder dibatasi ACL operator; config backup bisa
   berisi rahasia konfigurasi sehingga tidak boleh di-commit/dikirim ke chat.
3. Pasang server.crt/server.key/CA publik di subfolder unik PGDATA/dpr-tls.
   Private key server owner postgres mode 0600; CA key tetap di luar container.
4. `ALTER SYSTEM` mengatur ssl_cert_file, ssl_key_file, ssl_min_protocol_version
   TLSv1.2, ssl=on; `pg_reload_conf()` tanpa restart atau recreate.
5. Verifikasi TLS PostgreSQL SSLRequest, CA+hostname dan fingerprint leaf.
6. Prepend dua aturan hostnossl reject (IPv4/IPv6) **hanya** untuk tiga database
   proyek. Aturan auth lain dipertahankan, koneksi Unix socket tetap berjalan.
   Parse pg_hba_file_rules, reload, uji koneksi tanpa TLS ditolak.
7. Verifikasi ID container, waktu mulai postmaster, dan OID database tidak berubah.
   Tidak ada pembacaan/penulisan baris data anggota.

ssl=on sendiri memungkinkan koneksi SSL dan non-SSL; aturan HBA di atas menolak
non-SSL untuk database proyek. Koneksi yang sudah terbuka tidak diputus paksa.
Aturan autentikasi lama tidak diganti menjadi trust atau metode lain. Role/GRANT
aplikasi tetap pekerjaan tahap skema/role; TLS bukan pengganti autentikasi.

Kegagalan setelah pengaturan SSL memicu rollback setting SSL/HBA sebelumnya.
Rollback eksplisit, jika diperlukan:

```powershell
$state = Get-ChildItem -LiteralPath (Join-Path $env:DPR_SECRETS_DIR 'postgres\changes') -Filter state.json -Recurse |
    Sort-Object LastWriteTime | Select-Object -Last 1
.\.venv\Scripts\python.exe -m infra.postgres.enable_tls rollback --state $state.FullName
```

Rollback memeriksa ID container dan integritas snapshot, menolak jika HBA/setting
SSL diubah pihak lain sejak snapshot. Hanya empat parameter SSL disentuh, tidak
memakai ALTER SYSTEM RESET ALL atau menimpa perubahan konfigurasi lain.
Sertifikat berlaku 30 hari; siapkan renewal terencana sebelum kedaluwarsa.

## Koneksi A/B/C

Semua client memakai `sslmode=verify-full` + `sslrootcert`/PGSSLROOTCERT menunjuk
CA publik `DPR_SECRETS_DIR\postgres\tls\ca.crt`. Sebarkan **CA publik saja** ke
mesin/container client. Password dari env, bukan literal DSN di kode/history/log.

| Pemakai | Host dari Windows | Port host | Database |
|---|---|---|---|
| API MODE=plain / benchmark | 127.0.0.1 | 5433 | baseline_100k |
| API MODE=protected / migrasi | 127.0.0.1 | 5433 | protected_734 atau protected_100k |
| Sumber migrasi demo | 127.0.0.1 | 5433 | postgres, transaksi read-only |
| OpenBao | https://127.0.0.1 | 8200 | Transit |

API dalam Docker Desktop memakai host.docker.internal:5433 dan CA yang dipasang
read-only, atau koneksi jaringan Docker bersama ke pg-dpr:5432 (port internal).
Kedua nama tersebut ada di SAN default. Pilih jalur yang benar-benar dapat
dijangkau di lingkungan deployment, tetap ke instance/data yang sama.

Modul B/Zhafif harus mengubah konfigurasi stack yang dimilikinya: tidak memakai
protected-db/baseline-db PostgreSQL 17 pada docker-compose.yml lama. Kode lama
belum memiliki pemilihan MODE sesuai kontrak; dokumen ini bukan klaim bahwa API
sudah beralih. Tidak mengubah aplikasi atau Compose lama milik B dari Modul A.
Modul C perlu memakai CA publik/verify-full saat benchmark/scanner berikutnya dan
merekam konfigurasi TLS yang sama pada before/after. Baseline tidak dibuat ulang.

Modul A menyediakan `migration.connection.connection_parameters(database,
source=False)`: hanya target protected_734/protected_100k, wajib port 5433,
TLS verify-full, role/password env. Untuk sumber, `source=True` hanya menerima
postgres/baseline_100k dan memasang default_transaction_read_only=on. Helper ini
tidak menjalankan migrasi atau membuat database target sebelum tahap skema.

## Pengujian dan evidence

```powershell
$env:DPR_POSTGRES_TLS_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m pytest infra/tests/test_postgres_tls.py infra/tests/test_postgres_tls_integration.py -q --tb=short
Remove-Item Env:DPR_POSTGRES_TLS_INTEGRATION
```

Test integrasi membuat PostgreSQL 18 disposable pada port acak, menambahkan
hanya baris sintetis, menguji reload/rollback/keutuhan row dan container, kemudian
menghapus hanya project uji tersebut. Bukan pengganti penerapan ke pg-dpr asli.
`evidence/infra/postgres-tls-integration.json` membedakan scope disposable;
`evidence/infra/postgres-tls.json` mencatat inspect/apply/verify instance yang
diminta. Status gagal/unavailable tidak boleh dilaporkan sebagai TLS sudah aktif.

Sumber primer: [TLS server PostgreSQL 18](https://www.postgresql.org/docs/18/ssl-tcp.html),
[HBA PostgreSQL 18](https://www.postgresql.org/docs/18/auth-pg-hba-conf.html),
[verify-full libpq](https://www.postgresql.org/docs/18/libpq-ssl.html), dan
[ALTER SYSTEM](https://www.postgresql.org/docs/18/sql-altersystem.html).
