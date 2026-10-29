# Panduan reproduksi lengkap — 734 record

Panduan utama untuk juri/pengembang baru. Jalankan dari root sumber aktif.
Alur di bawah membuat **lingkungan baru terisolasi**, bukan mengubah server
existing. Tidak membutuhkan `.env`, password, token atau akun dari laptop tim.

## 1. Prasyarat

- Python **3.11+** dengan `venv` dan `pip`; diuji dengan interpreter yang dicatat
  di evidence run, bukan menganggap seluruh versi/platform sudah diuji.
- Node.js **≥20.9**, npm, akses registry paket untuk instalasi awal.
- Docker Engine Linux + **Compose V2** yang berjalan; user diizinkan mengakses engine.
  Pada Windows gunakan Docker Desktop Linux containers. Alternatif native ada di §7.
- **Google Chrome** terpasang. Playwright menggunakan `channel: chrome`; memasang
  dependency npm saja tidak memasang Chrome. Tanpa Chrome, verifikasi browser FAIL.
- Input resmi panitia **734 record**, `02_data.sql`, diberikan secara privat.
  Source ZIP publik tidak memuat dataset. Jangan mengunduh SQL dari sumber lain,
  membuat 734 baris sembarang lalu mengklaim data panitia, atau memublikasikannya.
- RAM/disk cukup untuk PostgreSQL 18, OpenBao 2.5.5, build Next.js dan browser.
  Tidak perlu menyediakan port 5433/8200/3443 tertentu: launcher memilih port acak.

Git diperlukan untuk clone; sumber yang diekstrak dapat dijalankan tanpa Git.
Jangan menjalankan launcher sebagai root pada Linux; PostgreSQL native juga
menolak initdb sebagai root. Rahasia dibuat owner-only di luar checkout.

## 2. Setup satu kali

PowerShell, Linux dan macOS (dengan prasyarat kompatibel) menggunakan interface sama:

```powershell
python -m infra.reproduce setup
```

Di Linux yang hanya menyediakan `python3`, gunakan `python3` atau `make PYTHON=python3 setup`.
Setup membuat `.venv` untuk A/B serta `.venv-assessment` untuk scanner/datagen,
memasang requirements, editable toolkit, menjalankan `pip check`, `npm ci` dan
`npm run build`. Pin psycopg A/B **3.3.3** dan C **3.3.6** sengaja terpisah.
Cryptography sekarang **≥50.0.2,<51**, pytest **9.0.3** sesuai manifest aktif.
Setup tidak membuka database atau OpenBao existing. Ini environment development,
bukan Docker build dengan daftar OS/transitive dependency terkunci penuh.

Status mesin setup: `evidence/reproduction/generated/setup.json` (lokal, diabaikan Git).
Jika gagal instalasi/build, launcher keluar nonzero, jangan lanjut demo.

## 3. Verifikasi end-to-end tanpa menyentuh data tim

```powershell
python -m infra.reproduce verify --data "C:/private/02_data.sql"
```

Linux: ganti input dengan path privat Linux. Pada private clone yang memang memuat
`sql/baseline/02_data.sql`, `--data` boleh dihilangkan. Alternatif non-secret env:
`DPR_DEMO_DATA=<absolute input path>`. Bukan isi SQL/password yang dimasukkan lewat env.

Tahap yang dijalankan:

1. Membuat direktori privat baru dan stack acak `dpr-repro-<random>` dengan port
   loopback acak. Docker hanya memasang password file dan leaf certificate yang
   dibutuhkan; CA signing key dan bootstrap root/shares tidak dipasang ke service.
2. Membuat CA lokal, PostgreSQL TLS dan OpenBao **server biasa**, bukan Bao dev mode.
   Key plane baru di-init/unseal hanya untuk demo disposable ini. Root+3 shares
   sementara tersimpan privat di luar Git. Ini bukan konfigurasi custody produksi.
3. Memparse literal INSERT sumber, mengimpor 734 record ke DB `postgres` milik
   cluster baru. Tidak mengeksekusi dump sebagai SQL bebas, tidak menjalankan DROP.
   DB `postgres` pada pg-dpr tim sama sekali tidak dihubungi.
4. Menjalankan scanner read-only dengan `scanner_user`, menulis inventory,
   klasifikasi, relasi, k-anonymity dan evaluasi acuan. Membangun profile **dari
   inventory run ini** + override tim/kontrak; profile sumber tidak ditimpa.
5. Menerapkan skema dan role minimum pada DB BARU `protected_734`; migrasi memakai
   `migration_user` dan token `svc-migration`, validator token `svc-app`. Semua
   734 record/semua field, NULL dan blind index dibandingkan di memori. Run kedua
   membuktikan resume selesai tanpa duplikasi. Token migrasi dicabut, role NOLOGIN.
6. Menerapkan tabel kontrol B dan unique index F-01. Enam akun demo dibuat dengan
   password acak Argon2id; assignment read/update hanya record 1 dan 2, anggota
   terikat tepat satu record. Ini assignment fixture, bukan seluruh 734 boleh diakses
   semua role. `svc-app` dan role DB workload digunakan runtime; bukan root/DBA.
7. Memeriksa TLS benar, koneksi tanpa TLS/hostname salah ditolak, default RLS menolak
   akses tanpa principal, analyst/auditor ditolak membaca tabel/view per record,
   agregat hanya k≥5, serta test vectors/tamper/swap/nonce.
8. Backup `pg_dump -Fc` di-stream ke enkripsi dengan dua kunci backup/HMAC terpisah.
   Restore tanpa OpenBao (tetap ciphertext), restore dengan OpenBao + smoke decrypt,
   tamper satu byte dan retention drill dijalankan ke DB BARU. Penghapusan retention
   hanya pada clone buatan drill; tidak pada sumber hasil migrasi.
9. Menjalankan backend dan Next HTTPS di atas DB hasil restore, lalu **Chrome nyata**
   untuk enam akun: role/field/record, raw JSON, analytics, cookies, storage dan logout.
   Probe tidak memodifikasi record anggota. Bandingkan source hash untuk memastikan
   input cluster baru tetap sama. Akun/sesi/audit login normal dapat berubah.
10. Menghentikan proses/project invocation; Docker menghapus hanya volume milik project
    acak. Cluster native dihentikan; material privat dipertahankan untuk pemeriksaan.

Hasil `evidence/reproduction/<run-id>/summary.json`; setiap run mempunyai direktori
baru, tidak menimpa evidence final/historis. `passed=false`/exit nonzero berarti gagal.
Baca `failed_stage`, `security.json`, `browser.json`, `migration.json` dan laporan
backup/restore. `NOT_RUN`/skip bukan PASS. Ini acceptance, **bukan benchmark resmi**.

## 4. Demo interaktif

```powershell
python -m infra.reproduce demo --data "C:/private/02_data.sql"
```

Demo menjalankan alur yang sama, kemudian mempertahankan service HTTPS sampai
Ctrl+C. Launcher menampilkan URL `/login`, path file akun privat dan CA browser;
**tidak mencetak username/password atau token**. Buka file akun sendiri secara
lokal; jangan tampilkan pada proyektor atau mengirim isinya ke chat.

Sertifikat dari CA lokal belum otomatis dipercaya OS/browser. Untuk membuka demo
manual, percayai **CA run tersebut** pada profil browser uji sesuai prosedur browser,
atau gunakan hasil probe Chrome otomatis yang hanya mem-pin SPKI sertifikat run ini.
Jangan memakai bypass TLS global, `NODE_TLS_REJECT_UNAUTHORIZED=0` atau `verify=False`.
Tidak ada perubahan trust store OS otomatis. Hapus trust CA demo setelah selesai.

Token workload demo maksimal satu jam. Bila kedaluwarsa, hentikan lalu buat run baru;
jangan memasukkan root token ke aplikasi atau menganggap ada auto-renewal produksi.
Ctrl+C menghentikan service milik run. Setelah selesai, folder privat run di direktori
`<temporary-directory>/dpr-reproduction/<run-id>/` boleh dihapus operator bila tidak
lagi diperlukan. Folder itu bisa berisi cluster plaintext sumber dan recovery keys;
**tidak termasuk submission**. Penghapusan biasa tidak diklaim secure erase media.

## 5. Make tersedia, PowerShell tidak wajib memasangnya

```text
make setup
make verify DATA=/private/02_data.sql
make demo DATA=/private/02_data.sql
make test
```

Semua target memanggil launcher yang sama. `make test` setara
`python -m infra.reproduce test`: suite A, B dan scanner/datagen terpisah. Integrasi
lain tetap opt-in. Command test bukan pengganti `verify` yang memakai service nyata.

## 6. Troubleshooting tanpa membocorkan rahasia

| Gejala | Tindakan |
|---|---|
| `preflight` FAIL | Periksa input 734 literal INSERT, `setup`, Chrome dan environment assessment |
| Docker engine tidak tersedia | Nyalakan/restart Docker Desktop; periksa `docker version`, `docker compose version`; gunakan native bila disiapkan |
| `setup` FAIL pada run | Periksa Docker image/versi, bind mount file privat dan hak non-root; jangan mengubah pg-dpr existing |
| `assessment` FAIL | Pastikan setup selesai dan sumber sesuai DDL; baca artefak scan baru tanpa mencetak DSN |
| `hardening` FAIL | Baca report tahap, jangan re-init key plane existing, jangan melewati validasi profile/dekripsi |
| `service_application` FAIL | Pastikan requirements A/B, F-01 dan input unik; jangan jalankan service sebagai admin |
| `security_verification` FAIL | Periksa hasil boolean DB/browser/restore; Chrome harus terpasang, frontend sudah build |
| Cleanup service FAIL | Identifikasi project `dpr-repro-...` milik run saja; jangan `docker system prune` atau menghentikan container tim |

Output pengecualian disembunyikan agar nilai pribadi/SQL/DSN tidak keluar. Ini dapat
mengurangi detail diagnosis; investigator memakai folder privat run secara lokal.
Jangan commit config/env/password/log privat ketika memperbaiki prasyarat.

## 7. Alternatif native jika Docker tidak tersedia

Sediakan binary PostgreSQL **18** (`postgres`, `initdb`, `pg_ctl`, `psql`, `pg_dump`,
`pg_restore`) dan OpenBao **2.5.5** dari distribusi resmi sesuai OS. Periksa checksum
rilis sebelum eksekusi. Tidak ada path tool laptop tim yang dianggap default.

```powershell
python -m infra.reproduce verify --data "C:/private/02_data.sql" --native-pg-bin "C:/tools/pgsql/bin" --native-bao-bin "C:/tools/bao.exe"
# Argumen native yang sama juga diterima subcommand demo.
```

Native tetap cluster baru di luar repo, TLS wajib, role/schema/kripto/migrasi/backup
aplikasi yang sama. Transport psql/pg_dump/pg_restore berbeda dari Docker; evidence
mencatatnya. Tidak ada SQLite, respons API mock, mock crypto atau patch fungsi test
untuk menghasilkan hasil acceptance. OpenBao production tetap manual unseal.

## 8. Operasional existing dan reproduksi benchmark terpisah

Launcher bukan upgrade/deploy server existing. Untuk lingkungan tim gunakan:
[VM fresh](../../infra/vm/README.md), [TLS existing](../../infra/postgres/README.md),
[rilis A5](../../app/docs/DEPLOY_A5.md), [F-01](../../app/docs/F01_DUPLICATE_IDENTITY.md),
[migrasi](../../migration/README.md), [backup](../../scripts/backup/README.md),
[cutover restore](../../app/docs/RECOVERY.md), [rotasi](../../infra/rotation/README.md).
Jangan menyiapkan ulang skema, akun atau golden reset hanya untuk update kode.

Benchmark besar tidak dijalankan `setup`/`demo`/`verify`. Datagen dan runner sudah ada:

```powershell
python -m venv .venv-benchmark
.venv-benchmark/Scripts/python -m pip install -r benchmark/requirements.txt -e toolkit
.venv-benchmark/Scripts/python -m datagen --help
.venv-benchmark/Scripts/python -m benchmark --help
.venv-benchmark/Scripts/python -m benchmark.api --help
```

Linux ganti `Scripts/python` dengan `bin/python`. Untuk membangun baseline dari
734 record gunakan [datagen](../../datagen/README.md) dengan `--rows 100000` atau
`--rows 1000000`, seed **42**, target database baru, credential privat eksplisit.
Ikuti [benchmark DB](../../benchmark/README.md) dan [benchmark API](../../benchmark/api/README.md)
untuk preflight AC/power, snapshot, workload, B-P-P-B, raw, median dan target yang
sudah dibekukan. Jangan menjalankan bersamaan demo/test berat. Evidence lama tidak
ditulis ulang hanya untuk membuat angka lebih baik; perbandingan DB gagal target
latensi/throughput harus tetap dilaporkan. Pengecualian baseline non-TLS hanya untuk
bench/scanner pada database/IP yang disepakati, **tidak berlaku untuk protected**.

## 9. Luaran dan pemeriksaan paket tanpa membuat ZIP

```powershell
.venv/Scripts/python -m infra.submission sbom
.venv/Scripts/python -m infra.submission check
```

Regenerasi SBOM deklarasi sumber bukan audit CVE baru atau refresh evidence historis.
BOM/audit environment terbaru mempunyai scope tersendiri di [docs/sbom](../sbom/README.md).
Check memeriksa sumber aktif, tautan lokal, pola credential terbatas dan freshness
SBOM; bukan audit seluruh sejarah/log/PII atau bukti PDF/slide final sudah dibuat.
Pembuatan ZIP sengaja ditunda. [Checklist 15 luaran](../submission/CHECKLIST.md)
menyebut pekerjaan manusia/PDF/presentasi yang tetap harus diselesaikan.
