# Target clone benchmark API — handoff Zhafif ke Delf

Fitur B ini memilih clone yang disiapkan operator. Ia tidak membuat, menamai ulang
atau menghapus database, menjalankan benchmark, mengubah target performa, maupun
melakukan cleanup. Konfigurasi demo protected_734 terpisah dari benchmark laptop.

## Konfigurasi

Env **DPR_BENCHMARK_DATABASE** memilih satu database berpola
`api_[a-z0-9_]{1,59}` (maksimum63 karakter). Tanpa env ini, allowlist lama tetap
berlaku. Override postgres/baseline_100k/protected_734 ditolak. Pemilihan ini tidak
bisa digabung dengan DPR_RESTORED_DATABASE atau dipakai untuk bypass role/TLS.

Contoh tanpa secret, setelah clone disiapkan operator:

```powershell
$env:MODE = 'plain'
$targetDb = 'api_plain_100k_20261029'
$env:DPR_BENCHMARK_DATABASE = $targetDb
$env:APP_ORIGIN = 'https://127.0.0.1:8100'
$env:API_PORT = '8100'
```

Untuk protected, gunakan MODE=protected dan clone lain, misalnya
api_protected_100k_20261029. Endpoint, DTO, autentikasi, audit, rate limit dan crypto
adapter tetap memakai kode yang sama pada dua mode.

Isi URL lewat secret store/helper Set-ServiceDbUrl pada app/README.md:

| Env | Role | Database |
|---|---|---|
| DATABASE_URL | app_user | clone yang dipilih |
| AUTH_DATABASE_URL, jika diisi | app_user | clone yang sama |
| ANALYST_DATABASE_URL, jika diisi | analyst_user | clone yang sama |
| AUDITOR_DATABASE_URL, jika diisi | auditor_user | clone yang sama |
| APP_SETUP_DATABASE_URL, hanya setup | postgres | clone yang sama |

Semua URL harus memakai host/port/database yang sama, sslmode=verify-full dan
sslrootcert file existing. Runtime tetap menolak role postgres/bench_user dan TLS
yang lebih lemah. Nilai secret/URL lengkap tidak boleh dicetak.

## Urutan operator

1. Delf/Alby memastikan recovery eksperimen lama selesai dan OID/checksum original
   cocok; journal restore_failed harus diselesaikan sebelum run baru. Laporan lama
   bukan bukti keadaan live terbaru. Perbaikan B tidak melakukan recovery otomatis.
2. Operator C membuat clone api_ yang berbeda untuk plain/protected. COPY/template,
   ownership OID, checksum corpus dan cleanup tetap dikelola A/C.
3. Isi env di atas, private directory berbeda per clone di luar repo, serta CA dan
   TLS_CERT_FILE/TLS_KEY_FILE lokal dengan SAN yang sesuai URL. Protected memerlukan
   token svc-app dan CA OpenBao yang masih berlaku. Jalankan:

```powershell
.\app\.venv\Scripts\python.exe app/scripts/schema.py --database $targetDb
# Isi DPR_PRIVATE_DIR, DEMO_MEMBER_PRINCIPAL, DEMO_ASSIGNED_IDS (protected)
# dari fixture/korpus sintetis yang disetujui, tanpa menampilkannya ke output.
.\app\.venv\Scripts\python.exe app/scripts/provision.py
```

Schema CLI menggunakan MODE untuk memilih plain/protected, bukan prefix nama DB.
Ia memeriksa database/TLS/tabel anggota, memberi CONNECT pada clone kepada tiga role
runtime serta USAGE pada schema public. CONNECT adalah hak database, USAGE adalah
hak schema. Prasyarat ini perlu ditinjau setelah CREATE DATABASE TEMPLATE.
Tidak ada pembuatan role atau DDL bagi app_user.

Setup memberi comment dpr-service-benchmark-v1:plain atau :protected pada clone.
Marker menyatakan persetujuan setup, **bukan bukti integritas/asal clone**; OID dan
checksum tetap kewajiban C. Runtime membaca metadata secara read-only: marker harus
cocok, user app_user, TLS aktif, tanpa superuser/BYPASSRLS/DDL/membership berlebih,
tabel kontrol lengkap serta owner schema_owner/FORCE RLS pada protected. Setup
parsial tidak cukup jika tabel yang diperlukan belum lengkap. Gagal startup menutup
koneksi/provider, tanpa fallback ke database original.

Provisioning tetap memakai Argon2id/random dan file privat, menolak akun/file yang
sudah ada. Jangan provision ulang akun demo VM. Scope dan populasi akun benchmark
plain/protected harus disamakan operator pada clone, mencakup korpus pengujian.

4. Sebelum menjalankan service anak, bersihkan environment setup:

```powershell
Remove-Item Env:APP_SETUP_DATABASE_URL,Env:DEMO_MEMBER_PRINCIPAL -ErrorAction SilentlyContinue
.\app\.venv\Scripts\python.exe app/scripts/serve.py
```

Runner C yang menyusun child env dari allowlist perlu memasukkan
**DPR_BENCHMARK_DATABASE=clone_name**, mengganti database pada seluruh URL, argumen
schema --database serta koneksi setup/provision agar cocok. Fitur ini tidak otomatis
mengubah runner lama yang masih menukar nama original.

## Prasyarat A/C yang tetap berlaku

- Load generator memvalidasi HTTPS lewat file CA. Klien Python C sudah memakai
  SSLContext(cafile=...); launcher k6 Windows pada commit10e4cc8 masih memeriksa
  CurrentUser/Root. Perubahan B tidak menonaktifkan TLS atau mengganti load generator.
- HBA/operator mengizinkan koneksi TLS/SCRAM ke clone api_ untuk role yang diperlukan.
  App verify-full bukan bukti bahwa server menolak non-TLS untuk semua role; kebijakan
  TLS server pada clone protected perlu diverifikasi A. Tidak ada perubahan HBA oleh B.
- APP_ORIGIN cocok dengan base URL benchmark. Domain demo berbeda dari endpoint
  API lokal; CSRF/origin tetap diperiksa. Rate limit/cooldown dan token expiry tetap
  harus ditangani eksperimen, bukan dinonaktifkan untuk memperbaiki skor.
- Worker cleanup, restore, source hash, dataset/hardware dan target performa tetap
  kewajiban eksperimen C. Jangan mencampur hasil lama dengan kode/config baru.

Hasil live benchmark untuk fitur ini: **NOT TESTED**. Tes B hanya memakai fixture
sintetis/mocked PostgreSQL metadata, tanpa koneksi database tim atau menjalankan runner.
