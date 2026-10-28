# Pemulihan aplikasi dari backup A+B

Gunakan kode A/B terbaru pada operator backup dan aplikasi. Backup layanan mencakup
tujuh tabel: lima tabel A ditambah `service_sessions` dan `service_member_bindings`,
beserta `service_legacy_id_seq`. Backup lima tabel lama tetap didukung untuk pemulihan
data; akun/sesi/binding B yang tidak ada dalam arsip tidak dapat dipulihkan dari arsip itu.

## Persiapan sekali pada instalasi existing

1. Muat environment PostgreSQL/OpenBao/CA dan kredensial existing secara privat,
   mengikuti README A/B. Jalankan updater TLS terbaru agar nama database restore
   juga menolak plaintext. Existing exception baseline bench/scanner tetap terbatas.

   ```powershell
   python -m infra.postgres.enable_tls apply
   python -m infra.postgres.enable_tls verify
   ```

2. Sebelum membuat backup layanan baru, jalankan ulang setup B pada protected target
   existing menggunakan `APP_SETUP_DATABASE_URL` trusted operator, TLS verify-full.
   Ini menambahkan SELECT sequence untuk backup_user, tidak mereset sequence/akun.

   ```powershell
   python app/scripts/schema.py --database protected_734
   # Pilih protected_100k / protected_1m bila itu database layanan yang dipakai.
   Remove-Item Env:APP_SETUP_DATABASE_URL -ErrorAction SilentlyContinue
   ```

## Backup dan restore ke target baru

Gunakan environment dan pilihan `--local-credentials` sesuai README backup. Kunci
enkripsi backup dan HMAC harus sama dengan yang digunakan untuk membuat arsip.
OpenBao harus menyediakan KEK versi yang dibutuhkan wrapped DEK. Jangan init ulang
OpenBao, mengganti kunci backup lama, atau memakai root token di aplikasi.

```powershell
python -m scripts.backup --local-credentials backup --source protected_734
# Isi $manifest dengan path manifest yang baru dibuat (path bukan secret).
python -m scripts.backup --local-credentials restore --manifest $manifest --with-openbao
$recovery = Get-Content -Raw evidence/backup/restore-report.json | ConvertFrom-Json
if (-not $recovery.passed -or -not $recovery.service_schema_restored) {
    throw 'Restore layanan belum tervalidasi; jangan alihkan aplikasi'
}
```

Restore memverifikasi HMAC/SHA/AEAD sebelum CREATE DB; target harus fresh dan bernama
`dpr_restore_<32 hex>`. Count seluruh tujuh tabel, owner/grant/RLS, dan allocator insert
divalidasi sebelum marker dan CONNECT dipublish. `--with-openbao` juga mengautentikasi
field sampel; pemeriksaan HTTPS aplikasi berikut tetap diperlukan.

Tanpa `--with-openbao`, ciphertext dan tabel kontrol dipulihkan tanpa memakai OpenBao.
Pemulihan dekripsi layanan memerlukan akses key plane yang sah ketika aplikasi dibuka.
Restore tanpa key plane tidak menjanjikan pengguna bisa membaca field terenkripsi.

## Cutover yang dipilih operator

Hentikan API lama sebelum mengganti environment. Pakai helper `Set-ServiceDbUrl` dari
`app/README.md` yang meminta password tersembunyi. Gunakan CA server yang sama; semua
URL harus menunjuk host, port, dan database restore yang sama.

```powershell
$env:MODE = 'protected'
$env:DPR_RESTORED_DATABASE = $recovery.database
Set-ServiceDbUrl 'DATABASE_URL' 'app_user' $recovery.database
Set-ServiceDbUrl 'AUTH_DATABASE_URL' 'app_user' $recovery.database
Set-ServiceDbUrl 'ANALYST_DATABASE_URL' 'analyst_user' $recovery.database
Set-ServiceDbUrl 'AUDITOR_DATABASE_URL' 'auditor_user' $recovery.database
# OPENBAO_ADDR/CACERT/TOKEN svc-app, APP_ORIGIN dan TLS_CERT_FILE/TLS_KEY_FILE
# sudah diisi melalui penyediaan rahasia lokal, sesuai README B.
python app/scripts/serve.py
```

Startup memeriksa database yang dipilih persis, TLS, app_user tanpa hak istimewa,
marker layanan hasil restore, tujuh tabel, ownership dan FORCE RLS. Guard tidak
menerima database lain hanya karena namanya memiliki prefix restore. Tidak ada
fallback plain. Akun, binding dan scope berasal dari backup; jangan provision ulang.
Sesi existing tetap mengikuti expiry aslinya; operator dapat memilih pencabutan sesi
terpisah sesuai kebijakan insiden. Marker adalah metadata operator, bukan pengganti
autentikasi kriptografis arsip atau perlindungan dari DBA superuser yang berbahaya.

Buka web HTTPS dengan konfigurasi backend/CA yang sama. Periksa login, daftar/detail,
pencarian, update kontak, insert officer, serta deny role/record yang diwajibkan.
Evidence otomatis: `evidence/backup/service-recovery-integration.json` menggunakan
fixture buatan sendiri dan HTTPS backend; bukan benchmark atau hasil dataset resmi.

Rollback koneksi: hentikan API, hapus `DPR_RESTORED_DATABASE`, lalu set ulang keempat
URL ke database protected sebelumnya dan jalankan API. Tidak perlu menghapus atau
menimpa database sebelumnya untuk mencoba restore/cutover.
