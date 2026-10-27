# Pemeriksaan awal tahap 4 — 27 Oktober 2026

Sinkronisasi dengan main `20e08f3`: belum menjalankan migrasi atau menulis data
anggota ke protected_734/protected_100k. Tidak diperlukan dump tambahan untuk
clone development lokal: file 02_data.sql identik dengan main dan source 734
serta baseline 100k sudah tersedia. Verifikasi read-only kembali lulus untuk
checksum kedua sumber dan TLS seluruh DB (`evidence/development/verify.json`).
Bukti baseline awal DB C tersedia: 21 run dan 3 restore berhasil. Bukti itu
tidak menggantikan benchmark API/eksperimen B-P-P-B yang masih terpisah.

OpenBao lokal 2.5.5 terjangkau melalui verified TLS, tetapi initialized=false,
sealed=true pada pemeriksaan status. Init/unseal manual, konfigurasi Transit,
dan penerbitan token workload diperlukan sebelum migrasi nyata. Tidak ada root
token atau unseal share yang perlu dimasukkan ke repo. Material recovery berada
di DPR_SECRETS_DIR eksternal; service memakai env/token ber-TTL terbatas.
svc-migration tidak boleh decrypt; decrypt-and-compare harus menggunakan
identitas decrypt yang terpisah dan diizinkan, bukan memperluas policy migrasi.

Handoff Service App yang kini tersedia di main memerlukan sinkronisasi kode:

- B mengharapkan factory dprcrypto:create_service dan lima method adapter; A
  saat ini menyediakan primitive OpenBaoClient/KeyManager/BlindIndexer/codec.
- B memakai users/sessions dan bentuk audit_log yang berbeda dari app_users
  serta audit metadata tahap 3 A. Jangan menjalankan bootstrap B langsung pada
  skema protected A sebelum kedua bentuk diselaraskan.
- Principal protected B adalah hex blind index pengguna (binding bidx:v1:hex),
  sementara access_scope/request_principal A memakai UUID akun. Kedua identitas
  tidak dapat langsung dipertukarkan; jangan melemahkan RLS agar tes lolos.
- Locator HTTP B adalah legacy_row_id; migrasi mempertahankan ID sumber di situ.
  AAD tetap menggunakan UUIDv4 internal anggota_id, sesuai kontrak.

Ini pekerjaan integrasi kode, bukan kekurangan file yang harus disuplai pengguna.
Folder app/ tetap milik B; koordinasi perubahan tidak boleh mengubah format
kriptografi kontrak v1 secara sepihak. Rujukan B: app/docs/CRYPTO_ADAPTER.md,
app/docs/LOCAL_LAB.md, app/backend/service_app/models.py.

## Implementasi tahap 4

CLI `python -m migration` menyediakan prepare/check/run/validate/revoke; panduan
env dan perintah lengkap ada di README modul. prepare memakai admin terpisah,
membuat hanya nama DB target allowlist bila belum ada via template1, lalu
bootstrap skema/role menggunakan infra. Source tidak mendapat DDL/DML/GRANT.
Run membatasi pasangan postgres->protected_734, baseline_100k->protected_100k;
target wajib migration_user tanpa atribut istimewa, source memakai READ ONLY.

Tabel `public.migration_jobs` (sql/protected/02_migration.sql) menyimpan satu job
per target: identitas source, hash seluruh source terurut, hash profile, jumlah
source/migrated, legacy ID terakhir, jumlah batch dan status. Hanya metadata;
tidak menyimpan per-cell hash, data pribadi atau kunci. migration_user hanya
SELECT/INSERT/UPDATE kontrol, backup_user SELECT, runtime app tidak punya hak.
Owner tetap schema_owner NOLOGIN. Kedua DB yang telah disiapkan tahap 3 dapat
ditingkatkan dengan prepare tanpa menghapus data/skema.

Resume memakai keyset id terurut dan UNIQUE legacy_row_id. Baris dan progres
commit bersama; tidak ada ON CONFLICT DO NOTHING yang menyembunyikan konflik.
Target nonkosong tanpa job, fingerprint berubah atau checkpoint/count/max tidak
cocok ditolak. Satu session advisory lock per target menolak migrator bersamaan.
Tidak ada retry/repair destruktif; ulangi perintah setelah dependensi pulih.

Per record: UUIDv4, DEK_PII+DEK_FIN CSPRNG 32 byte baru, wrap Transit batch,
AES-256-GCM lokal per field/AAD v1, HMAC batch search-hmac versi1, age_band.
Maksimal 100 record DEK per frame crypto; output batch hanya ciphertext/wrapped
DEK/bidx/REF/age_band. Tidak ada DEK diserialisasi, di-cache di disk, atau dicatat.
Python tidak menjamin penghapusan seluruh salinan immutable bytes dari RAM;
list menjadi tidak terjangkau sesudah pemrosesan. Ini tetap batas data in use.

Tanggal di-ISO-kan, integer ke desimal, string asli dipertahankan (termasuk nol
awal). NULL tetap NULL. Normalisasi hanya untuk HMAC, bukan plaintext yang
dienkripsi. age_band memakai usia selesai per 2026-10-01, interval 10 tahun;
tanggal lahir invalid/masa depan ditolak, tidak diganti nilai default.

Validasi selalu seluruh record, bukan sampling: ambil kembali DB, unwrap memakai
svc-app terpisah, decrypt-and-compare 25 field, bandingkan 4 REF + age_band,
hitung NULL dan HMAC lagi, cek count serta uniqueness nilai ternormalisasi yang
unik. Validation-only tetap bisa berjalan setelah svc-migration dicabut.
Marker valid lama dibatalkan sebelum validasi, sehingga rollback karena tamper
tidak meninggalkan status validated yang menyesatkan.

Source dibaca dalam snapshot REPEATABLE READ READ ONLY, lalu fingerprint dicek
lagi dalam snapshot baru sebelum/sesudah pembandingan. Target dikunci SHARE
selama validasi hingga marker validated commit. Tetap jalankan migrasi dalam
maintenance window tanpa penulis aplikasi/benchmark: advisory lock hanya
mengikat migrator yang mematuhinya; snapshot tidak membekukan penulis source.
Perubahan yang commit setelah pemeriksaan terakhir ada di luar jaminan snapshot
hasil migrasi. Source asli/clone lokal tetap dijaga tidak berubah oleh migrator.

Default run mencabut token svc-migration setelah validasi lulus; revoke eksplisit
tersedia, memeriksa policy tepat svc-migration. Tidak mencabut token validator
secara otomatis karena bisa merupakan token aplikasi yang masih diperlukan;
operator harus menjaga/mengganti token validasi sesuai tujuan dan TTL. LOGIN DB
migration_user juga belum otomatis dicabut karena berlaku global pada dua DB;
pemilik DB perlu mencabutnya setelah seluruh target selesai dan verifikasi final.

Adaptasi Onno: migrate.py memberi pola batch/progres, tetapi SELECT FOR UPDATE
SKIP LOCKED pada source, UUIDv5 deterministik, key env lokal bersama, dan
ON CONFLICT DO NOTHING tidak dipakai. Pilihan tim adalah source read-only,
UUIDv4, envelope dua domain, profile assessment, checkpoint atomik, serta
decrypt-and-compare dari database dengan token yang terpisah.

Rujukan API: [OpenBao Transit](https://openbao.org/docs/next/api/secret/transit/),
[PostgreSQL 18 transaksi](https://www.postgresql.org/docs/18/sql-set-transaction.html),
[advisory locks](https://www.postgresql.org/docs/18/explicit-locking.html#ADVISORY-LOCKS).
Dukungan batch/reference/HMAC dibuktikan pada image dipin 2.5.5 di integration
test; dokumentasi next bukan klaim versi runtime yang berbeda.

## Hasil implementasi dan dependensi lokal

Regresi lintas tests/infra/toolkit/policy/migration dengan semua flag integrasi
aktif dan DPR_MIGRATION_SCALE_ROWS=100000: **236 passed, 1 skipped** dalam
338,07 detik; satu skip fixture dataset historis, satu warning deprecation
Starlette dari aplikasi lama. Evidence JUnit: evidence/migration/tests-stage4.xml.
evidence/migration/integration-100k.json mencatat decrypt-and-compare seluruh
734 + 100000 record **buatan sendiri**, bukan corpus panitia/development tim.
Resume, kegagalan batch atomik, profile/source drift, checkpoint drift,
idempotensi, tamper ciphertext, token tanpa decrypt, concurrency lock dan
pencabutan token semuanya lulus. Ini uji fungsional, bukan benchmark resmi.

Penyempurnaan akhir menambahkan validasi policy pada check, penulisan report
atomik dengan nama temp unik/retry rename Windows, dan guard jumlah source
CLI tepat 734/100000. Guard mencegah source yang belum lengkap/terfilter RLS
dianggap migrasi penuh. Suite modul terakhir: **42 passed**, termasuk integrasi
734 + 1001 (evidence/migration/tests-final.xml, integration.json); ada 21
pemeriksaan integrasi terakhir. Uji awal 100k dipertahankan terpisah agar tidak
tertimpa suite cepat. Dua test baru report/policy menambah cakupan setelah
regresi gabungan; core perlindungan yang diuji pada skala 100k tidak berubah.

Prepare kedua DB lokal sudah PASS: tabel kontrol ditambahkan, role/grant
diterapkan, anggota/app_users/access_scope/audit_log tetap kosong. Source 734
dan baseline 100k lokal tetap cocok checksum resmi melalui verify read-only;
baseline seed42 yang sudah ada tidak diregenerate. Bukti prepare/readiness per
target berada di evidence/migration/, verifikasi source di evidence/development/.

Readiness lokal **belum PASS**: OpenBao initialized=false, sealed=true; env token
migrasi/validasi belum tersedia. Koneksi source READ ONLY + TLS, koneksi target
TLS/migration_user, profile serta tabel kontrol sudah memenuhi pemeriksaan.
Operator perlu init/unseal manual menurut infra/README.md, configure Transit,
issue token, kemudian mengisi env dan menjalankan check/run menurut README modul.
Tidak ada migrasi data nyata yang dijalankan dan tidak ada validation.json
development yang diklaim PASS. Sinkronisasi factory/akun/audit/principal dengan
B di bagian awal tetap pekerjaan integrasi Service App, tidak menghalangi migrator.
