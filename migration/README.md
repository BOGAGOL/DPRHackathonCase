# Migrasi tahap 4 — PowerShell

Status clone development Alby: kedua target sudah dimigrasikan dan tervalidasi
(734/100000), token migrasi dicabut, login DB migration_user NOLOGIN. Bukti:
evidence/migration/completion.json. Panduan berikut menjelaskan reproduksi saat
akses migrasi diaktifkan admin, bukan instruksi untuk mengulang setup otomatis.
Validasi ulang setelah penutupan akses memerlukan aktivasi LOGIN sementara oleh
admin (misalnya melalui prepare pada skema A yang masih cocok), kemudian NOLOGIN
lagi setelah selesai. Token svc-migration hanya diperlukan untuk run/revoke;
validate memakai svc-app.

Jalankan dari root repo, pada branch Modul A. Python 3.11+, Docker Desktop,
PostgreSQL 18 `pg-dpr:5433`, toolkit dprcrypto, PyYAML/psycopg dari requirements
infra diperlukan. Semua koneksi TCP PostgreSQL/OpenBao memverifikasi TLS dan CA.

```powershell
.\.venv\Scripts\python.exe -m pip install -r infra/requirements.txt -e toolkit
$env:DPR_SECRETS_DIR = Join-Path $env:LOCALAPPDATA 'DPR\crypto-infra-tls'
# Profile yang dikomit diperiksa prepare/run. Bangun ulang hanya untuk revisi
# assessment yang disengaja, bukan rutin setiap pull/resume:
# .\.venv\Scripts\python.exe -m policy.build_profile
# Fase admin eksplisit: buat DB bila belum ada, terapkan skema + role.
.\.venv\Scripts\python.exe -m migration prepare --target protected_734
.\.venv\Scripts\python.exe -m migration prepare --target protected_100k
```

`prepare` menggunakan admin env PGUSER/PGPASSWORD, atau admin DPAPI eksternal
yang sudah disiapkan infra. Pada laptop kosong, opsi
`--create-local-credentials` membuat ketujuh credential role DPAPI bila belum
ada. Tidak ada DROP/TRUNCATE/overwrite database. Target berisi anggota tanpa
checkpoint migrasi yang cocok ditolak oleh `run`. Target kosong dari tahap 3
memenuhi syarat fresh; menjalankan `prepare` lagi tidak merotasi password.

## Environment untuk proses migrasi

Source selalu READ ONLY. Credential source memakai DPR_SOURCE_USER dan
DPR_SOURCE_PASSWORD, dengan fallback PGUSER/PGPASSWORD; gunakan login SELECT
yang tersedia. Target selalu login `migration_user`, credential dari
DPR_MIGRATION_USER_PASSWORD. Runtime tidak memerlukan credential admin target.
Host/CA: PGHOST (default 127.0.0.1), PGPORT wajib 5433, PGSSLROOTCERT wajib ada.
Ekspektasi jumlah baris dibaca dari infra/database-targets.json:

| Source | Target | Bawaan expected_rows |
|---|---|---:|
| postgres | protected_734 | 734 |
| baseline_100k | protected_100k | 100000 |
| baseline_1m | protected_1m | 1000000 |

Jumlah lain dapat ditetapkan eksplisit melalui `--expected-rows N` pada
check/run/validate, termasuk saat resume. Nilai itu harus cocok dengan snapshot
source sebelum job/baris ditulis. Nama database tetap allowlist dan pasangan
source-target harus cocok; opsi ini tidak membuka target arbitrer atau overwrite
source. Skema/profile tetap sama. Default menjaga source yang belum lengkap atau
terfilter RLS tidak dianggap sebagai dataset penuh.

Contoh memuat credential lokal yang sudah disimpan DPAPI, tanpa menampilkannya:

```powershell
$sourceCredential = Import-Clixml -LiteralPath (Join-Path $env:DPR_SECRETS_DIR 'postgres\admin.credential.xml')
$migrationCredential = Import-Clixml -LiteralPath (Join-Path $env:DPR_SECRETS_DIR 'postgres\roles\migration_user.credential.xml')
$env:DPR_SOURCE_USER = $sourceCredential.UserName
$env:DPR_SOURCE_PASSWORD = $sourceCredential.GetNetworkCredential().Password
$env:DPR_MIGRATION_USER_PASSWORD = $migrationCredential.GetNetworkCredential().Password
$env:PGSSLROOTCERT = Join-Path $env:DPR_SECRETS_DIR 'postgres\tls\ca.crt'
$sourceCredential = $null
$migrationCredential = $null
$env:OPENBAO_ADDR = 'https://127.0.0.1:8200'
$env:OPENBAO_CACERT = Join-Path $env:DPR_SECRETS_DIR 'tls\ca.crt'
```

Pemakaian admin source di contoh hanya untuk clone development yang ada; query
migrator tetap SELECT dan transaksi READ ONLY. Jangan beri credential source
tersebut kepada Service App. Untuk lab lain, isi env login source SELECT yang
sudah diprovisikan oleh pemilik DB; migrator tidak mengubah privilege source.

Init/unseal OpenBao harus dilakukan manual menurut `infra/README.md`; sesudah
itu configure Transit dan issue token ber-TTL terbatas. Isi lewat env proses:

- OPENBAO_MIGRATION_TOKEN: hanya policy `svc-migration`, untuk wrap/HMAC.
- OPENBAO_VALIDATION_TOKEN: token berbeda, hanya policy `svc-app`, untuk unwrap
  dan HMAC pembanding. Jangan memakai svc-verify, root, atau menambah decrypt
  pada svc-migration. Token validator juga sensitif; scope kedua domain diperlukan
  untuk validasi migrasi tepercaya, bukan kredensial endpoint pengguna biasa.

File token hasil `infra.openbao.init issue` berada di folder eksternal
`openbao/tokens/`. Pilih file ber-TTL masih berlaku dari operator, lalu muat tanpa
echo; jangan menaruh token pada argv, source, Git, atau chat. OpenBao harus sudah
initialized/unsealed sebelum `check` bisa PASS.

## Jalankan, lanjutkan, dan validasi

```powershell
.\.venv\Scripts\python.exe -m migration check --source baseline_100k --target protected_100k
.\.venv\Scripts\python.exe -m migration run --source baseline_100k --target protected_100k --profile policy/protection_profile.yaml
# Mode demo sumber 734, dengan token migrasi baru bila token sebelumnya dicabut:
.\.venv\Scripts\python.exe -m migration run --source postgres --target protected_734 --profile policy/protection_profile.yaml
```

`run` memakai batch 1000 baris (boleh 1–1000 melalui `--batch-size`), crypto
Transit batch maksimal 100. Untuk pause terkendali gunakan `--max-batches 1`.
Jalankan ulang perintah yang sama untuk resume; tidak ada flag overwrite.
Batch yang gagal tidak memajukan checkpoint. Batch yang telah commit tidak
di-enkripsi ulang dan UUID/DEK/ciphertext tidak diganti. Source/profile berubah
atau target tidak cocok dengan checkpoint akan ditolak.

Setiap run selesai melakukan **decrypt-and-compare seluruh baris dan seluruh
field**, termasuk NULL, REF, age_band, HMAC yang dihitung ulang, jumlah record,
dan keunikan bidx jika nilai sumber yang dinormalisasi unik. Validasi membaca
kembali hasil dari database dan unwrap melalui identitas terpisah.

`run` secara default mencabut token svc-migration **setelah validasi berhasil**.
Jika sengaja menjalankan dua target dalam satu sesi, tambahkan
`--keep-migration-token` pada run pertama saja; run terakhir mencabut token.
Run paused/gagal tidak mencabut token, agar dapat di-resume selama TTL berlaku.
Token kedaluwarsa memerlukan penerbitan token baru, tidak memperpanjang TTL diam-diam.

```powershell
# Validasi ulang tidak memerlukan token svc-migration yang telah dicabut.
.\.venv\Scripts\python.exe -m migration validate --source postgres --target protected_734
# Pencabutan eksplisit bila sebelumnya memakai --keep-migration-token:
.\.venv\Scripts\python.exe -m migration revoke
```

Saat sesi selesai, hapus env credential/token dari proses PowerShell. Jangan
menyalin DEK ke file; kehilangan material recovery OpenBao menyebabkan wrapped
DEK di DB tidak dapat dibuka. Tidak ada fallback plaintext.

## Evidence dan pengujian

Hasil aktual ke `evidence/migration/validation.json` dan
`validation-protected_734.json`/`validation-protected_100k.json`; canonical file
menunjukkan hasil operasi terakhir, file per target menyimpan masing-masing hasil.
Pause ke `progress*.json`, kegagalan punya `passed=false`, persiapan ke
`prepare*.json`, dependency ke `readiness*.json`, pencabutan ke `revocation.json`.
Tidak ada nilai baris, DEK, token, password, atau respons error driver pada evidence.

```powershell
$env:DPR_MIGRATION_INTEGRATION = '1'
# Default: 734 + 1001 record buatan sendiri, bukan data panitia.
.\.venv\Scripts\python.exe -m pytest migration/tests toolkit/tests/test_transit_batches.py -q
# Uji skala penuh pada database/container SEMENTARA:
$env:DPR_MIGRATION_SCALE_ROWS = '100000'
.\.venv\Scripts\python.exe -m pytest migration/tests/test_integration.py -q
```

Test memakai CA/key/password/token sementara di luar checkout, PostgreSQL 18 dan
OpenBao 2.5.5 nyata, dua-duanya TLS verified. Source/target test memakai nama DB
kontrak tetapi berada di container acak, bukan pg-dpr pengguna. Tidak ada reimport
atau regenerasi baseline lokal. Evidence test ke `evidence/migration/integration.json`;
artefak itu **bukan** bukti migrasi development/resmi, dan tidak menggantikan
`validation.json` hasil eksekusi pada target sesungguhnya.

## Menjalankan target 1M di laptop benchmark

`baseline_1m` yang sudah dibentuk Modul C dipertahankan. Jangan mengulang datagen
atau menyalin database/kunci dari laptop lain hanya karena melakukan pull kode.
Siapkan infra lokal, credential dan CA sesuai panduan infra; konfirmasi baseline
1M milik C sebelum menulis target baru. Format blob/AAD/HMAC tetap protection v1.

```powershell
# Setelah env admin, runtime dan token workload disiapkan:
# Upgrade blok HBA lama ke allowlist TLS yang juga mencakup baseline_1m/protected_1m.
.\.venv\Scripts\python.exe -m infra.postgres.enable_tls apply
.\.venv\Scripts\python.exe -m migration prepare --target protected_1m
.\.venv\Scripts\python.exe -m migration check --source baseline_1m --target protected_1m
.\.venv\Scripts\python.exe -m migration run --source baseline_1m --target protected_1m --profile policy/protection_profile.yaml
```

Untuk ukuran development yang berbeda, tambahkan `--expected-rows` yang sama
pada check/run/validate, misalnya 12037. Ubah juga metadata perbandingan benchmark;
nama target protected_1m tidak membuktikan jumlahnya 1M jika override dipakai.
Token run 1M harus memiliki TTL cukup untuk operasi dan validasi penuh; operator
dapat menerbitkan TTL hingga 14400 detik menggunakan skrip infra. Tidak ada token
root pada migrator atau pembaruan TTL otomatis. Kegagalan/expiry mempertahankan
checkpoint; terbitkan token workload baru lalu ulangi perintah yang sama.

Prepare meningkatkan CHECK source_database pada tabel kontrol lama tanpa
menghapus job/data. Setelah semua run/verifikasi selesai, cabut token migrasi
(default run) dan nonaktifkan LOGIN role migrasi sementara sesuai prosedur admin.
HBA updater hanya mengganti blok lama yang persis dikenali, mempertahankan aturan
autentikasi lain, dan menolak blok yang telah diedit/duplikat.

Profile yang sudah dipakai checkpoint tidak perlu dibangun ulang hanya karena
checkout Windows/Linux. Loader memeriksa hash input LF/CRLF yang setara; CLI memakai
hash profile kanonik LF dan menerima hash legacy untuk byte profile yang sama.
Isi atau keputusan profile yang berbeda tetap menolak resume. Build profile
tetap untuk perubahan inventory/override/kontrak yang memang disengaja.

Uji 1M tanpa memakai corpus panitia atau mengubah pg-dpr lokal:

```powershell
$env:DPR_MIGRATION_INTEGRATION = '1'
$env:DPR_MIGRATION_1M_ROWS = '1000000'
.\.venv\Scripts\python.exe -m pytest migration/tests/test_integration.py -q
```

Fixture membuat source sendiri melalui COPY pada container acak, memakai TLS
OpenBao/PG18, menjalankan CLI 1M, lalu membandingkan seluruh record/field.
Resource diamati sebagai diagnostik uji fungsional, bukan benchmark resmi.
Awal uji 1M membutuhkan sedikitnya 6 GiB ruang host; proses dihentikan jika ruang
turun di bawah cadangan 2 GiB. Evidence skala penuh: integration-1m.json.
Batch menjaga DEK/row working set tetap kecil; summary keunikan menyimpan nilai
lookup ternormalisasi di RAM, sehingga kebutuhan memori mengikuti jumlah nilai
unik. Tidak ada nilai tersebut ditulis ke disk atau evidence.
