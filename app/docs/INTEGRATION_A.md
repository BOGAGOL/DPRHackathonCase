# Handoff Modul B setelah main b8e9998

Pemilik: Zhafif. Semua perubahan source/evidence ada di app/. Kode A dibaca/dipanggil
sebagai dependensi; toolkit, SQL A, migrasi, datagen C dan baseline_1m tidak dimodifikasi.

## Penyelarasan yang sudah diterapkan

- Factory: adapter ke OpenBaoClient/KeyManager/BlindIndexer/encrypt/decrypt aktual A.
- Akun: protected memakai app_users.user_id UUID dan hash Argon2id A. Sesi B disimpan
  di service_sessions, binding anggota di service_member_bindings.
- Principal: app.principal adalah UUID akun. Pengguna_bidx hanya untuk binding pemilik,
  bukan nilai principal RLS. Semua staff tunduk pada access_scope read/update/insert.
- Audit: INSERT hanya action, anggota_id UUID, field_class, decision, request_id.
  Actor/role/waktu ditetapkan trigger/default A. Kegagalan dekripsi dicatat sebagai error.
- Locator: URL tetap legacy_row_id; AAD tetap UUID internal. Sequence service_legacy_id_seq
  dibuat setelah migrasi oleh setup yang melihat semua record. Runtime tidak menghitung MAX
  dari subset RLS. INSERT tanpa RETURNING memungkinkan trigger A membuat scope record baru.
- Query/DTO minimal, masking, CSRF, cookie Secure/HttpOnly/Strict, CSP dan TLS tetap aktif.

## Menjalankan protected pada database hasil migrasi A

Prasyarat: migrasi A selesai dan tervalidasi pada target pilihan; OpenBao TLS telah tersedia;
workload token svc-app lokal, CA sendiri, Python 3.11+. Jangan memakai svc-migration/root
untuk aplikasi. Jangan regenerate baseline_1m. Prosedur migrasi tetap milik A.

Dari root repo, gunakan helper Set-ServiceDbUrl di app/README.md (password prompt tersembunyi).
APP_SETUP_DATABASE_URL diisi melalui secret injection dengan kredensial trusted setup A
pada host/port/database yang sama, verify-full, sslrootcert; jangan menggunakan app_user
untuk memberi dirinya sendiri scope. Setup harus melihat seluruh record dan dapat membuat
objek B, memindahkan ownership ke schema_owner, serta melakukan grant terbatas.

```powershell
$targetDb = 'protected_734' # atau protected_100k / protected_1m yang SUDAH dimigrasi
$env:MODE = 'protected'
Set-ServiceDbUrl 'DATABASE_URL' 'app_user' $targetDb
Set-ServiceDbUrl 'ANALYST_DATABASE_URL' 'analyst_user' $targetDb
Set-ServiceDbUrl 'AUDITOR_DATABASE_URL' 'auditor_user' $targetDb
# AUTH_DATABASE_URL opsional; bila diisi harus target yang sama dengan DATABASE_URL.
$env:DPR_CRYPTO_FACTORY = 'dprcrypto:public-v1'
# OPENBAO_ADDR, OPENBAO_CACERT, OPENBAO_TOKEN dan APP_SETUP_DATABASE_URL
# sudah diisi dari material lokal sendiri; jangan cetak environment.
app/.venv/Scripts/python app/scripts/schema.py --database $targetDb
$env:DEMO_ASSIGNED_IDS = '1,2' # contoh penugasan eksplisit, bukan seluruh dataset
# DPR_PRIVATE_DIR: direktori privat berbeda untuk setiap database target.
# DEMO_MEMBER_PRINCIPAL: pengguna sintetis target, baca dengan prompt tersembunyi README.
app/.venv/Scripts/python app/scripts/provision.py
Remove-Item Env:APP_SETUP_DATABASE_URL,Env:DEMO_MEMBER_PRINCIPAL -ErrorAction SilentlyContinue
# Isi TLS_CERT_FILE/TLS_KEY_FILE/APP_ORIGIN seperti README; kemudian:
app/.venv/Scripts/python app/scripts/serve.py
```

Provisioning sengaja menolak akun/file yang sudah ada, bukan menimpa akun atau izin A.
Untuk database dengan akun existing, admin A perlu memetakan assignment dan binding akun
secara eksplisit; skrip demo bukan migrator akun. Pengelolaan akun UI belum disediakan.
Setelah migrasi lanjutan menambahkan legacy ID, koordinasikan sequence sebelum membuka
insert aplikasi; setup idempotent tidak mereset sequence existing secara otomatis.

## Analytics A5 dan kontrak konsumen — 28 Oktober 2026

Mengikuti CONTRACT bagian 10.1 dan PR A #10. GET /analytics/summary hanya analyst,
menggunakan analyst_user untuk SELECT dimension, value, anggota_count dari
public.analyst_summary, diurutkan dimension dan value NULLS LAST. Backend tidak
membaca analyst_view atau tabel anggota untuk endpoint ini dan tidak melakukan count(*)
atau penjumlahan antar-marginal. Anggota_count dipetakan ke groups[].count (integer >=5).
Total selalu null; kelompok 1–4 termasuk labelnya tidak dikirim, tanpa placeholder <5.
Predicate anggota_count >=5 di query B juga menahan baris kecil dari view yang salah.

Query yang didukung: tanpa filter, ?dimension=nama_kppn, atau
?dimension=pekerjaan_terakhir&value=Guru. Pemilihan ini hanya memilih marginal yang
sudah dirilis SQL, bukan menghitung ulang cohort. Value memerlukan dimension.
Parameter anggota lama (nama_kppn, pekerjaan_terakhir, jenis_kelamin, nama_bank,
age_band) dan gabungannya ditolak 422; tidak ada fallback ke role atau proyeksi lama.
View hilang/permission ditolak menghasilkan 503 generik. Frontend menyediakan pemilih
dimensi/label saja; menampilkan total sebagai Tidak disediakan dan tidak merender
label kecil. NULL yang dirilis dengan count >=5 tetap didukung.

SQL A5 harus diterapkan terpisah dan terkoordinasi; pull/extract kode tidak mengubah
DB. Runbook VM B: [DEPLOY_A5.md](DEPLOY_A5.md), memanggil CLI kanonis A, tidak prepare
ulang. VM target hanya protected_734. Jangan menjalankan perubahan pada pg-dpr,
baseline_100k/protected_100k/protected_1m selama benchmark Delf berlangsung.
Baseline plain baru/disposable disiapkan B dengan view agregat ekuivalen. Perubahan
setup itu belum dijalankan pada lab existing; tunggu persetujuan waktu benchmark.

Batas: lima marginal ini bukan differential privacy, k-anonymity gabungan semua REF,
atau perlindungan mutlak dari inferensi lintas waktu/pengetahuan tambahan. Ciphertext,
AAD, bidx, protection_version, akun dan assignment tidak perlu diubah untuk A5.

## Bukti dan pekerjaan lintas tim

- protected-integration.json: fixture buatan sendiri, PG18 + OpenBao TLS nyata, schema/toolkit
  A asli, enam role, scope/RLS, audit trigger, insert, PATCH/bidx, AAD swap, revoke token,
  dan browser HTTPS. Resource Docker acak dibersihkan setelah uji.
- baseline-100k.json: validasi ulang lab lokal existing dengan datagen C seed42, checksum
  baseline/sumber kembali cocok setelah mutasi uji. Tidak ada regenerasi dataset.
- crypto-vectors.json: verifier toolkit A terhadap vectors bersama.
- unit-tests.json dan browser-tests.json: ringkasan tersanitasi, bukan dump data atau secret.

Local protected_734/100k/1m dan benchmark API resmi tetap NOT TESTED. Tidak ada migrasi
1M yang dijalankan B. Bukti disposable tidak sama dengan rows_compared:1000000.
Untuk perbandingan performa C, samakan workload, fixture dan cakupan record akun antar mode;
jangan memakai akun protected yang ditugaskan dua record untuk membandingkan scan100k penuh.
B tidak menjalankan benchmark bersamaan dengan mutasi integrasi atau migrasi.
