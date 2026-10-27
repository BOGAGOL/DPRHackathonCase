# Tahap 4 — 27 Oktober 2026

**Status terkini:** migrasi development lokal protected_734 (734 record) dan
protected_100k (100000 record) sudah tervalidasi seluruh field. Token migrasi
dicabut dan login DB migration_user dinonaktifkan. Bukti akhir ada di
evidence/migration/completion.json; catatan pemeriksaan awal berikut adalah
riwayat sebelum OpenBao diaktifkan, bukan status terkini.

**Pembaruan ukuran dataset:** CLI juga mendukung baseline_1m->protected_1m dan
--expected-rows pada check/run/validate. Uji fungsional 1.000.000 record buatan
sendiri telah lulus dengan pembandingan seluruh field; buktinya
evidence/migration/integration-1m.json. Target 1M uji berada di container
sementara yang sudah dibersihkan, bukan database development/benchmark resmi.

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

## Eksekusi aktual setelah unseal operator

Operator menginisialisasi dan melakukan unseal manual OpenBao 2.5.5. Konfigurasi
Transit tiga key dan empat policy diterapkan; token orphan tiap policy diterbitkan
TTL 3600 detik. Root hanya dipakai configure/issue lalu dihapus dari env proses;
material recovery/token tidak keluar dari direktori eksternal. Verifier OpenBao
PASS (evidence/infra/openbao.json) dan readiness dua target PASS sebelum migrasi.

Run postgres->protected_734 selesai dalam satu batch; token dipertahankan untuk
run baseline_100k->protected_100k yang selesai dalam 100 batch. Setiap target
menjalankan decrypt-and-compare semua record/field, NULL, REF/age_band, HMAC dan
uniqueness. Run terakhir mencabut token svc-migration. Validasi mandiri kedua
target **diulang setelah token tersebut dicabut**, memakai svc-app; keduanya
PASS. Hasil per target serta canonical validation.json adalah hasil aktual clone
development Alby, bukan angka benchmark resmi atau fixture disposable.

Verifikasi akhir memeriksa jumlah anggota/status job/fingerprint terhadap report,
penolakan lookup token migrasi yang sudah dicabut (HTTP403), dan checksum/TLS
source yang tetap cocok. Sesudah tidak ada sesi/member role migrasi, admin
mengubah migration_user menjadi NOLOGIN melalui koneksi template1. Objek/grant
role tetap ada untuk keperluan provisioning ulang oleh admin; tidak ada login
aplikasi atau backup yang dinonaktifkan. completion.json PASS merekam hasilnya.

Untuk run/validate ulang yang membutuhkan migration_user, admin perlu mengaktifkan
LOGIN sementara, kemudian menonaktifkannya lagi sesudah verifikasi. Misalnya
prepare pada skema A yang masih cocok mengaktifkan LOGIN kembali; aksi ini fase
admin eksplisit, bukan dilakukan otomatis oleh service. Token migrasi baru hanya
diperlukan untuk run, sedangkan validate memakai token svc-app yang masih valid.
Verifier empat policy memerlukan token migrasi baru jika ingin dijalankan lagi
setelah revokasi; bukti PASS yang disimpan berasal dari pemeriksaan sebelum run.

Integrasi factory/akun/audit/principal Service App dengan B tetap terpisah.
Tahap 5 backup/restore dapat memakai backup_user yang tetap aktif, dengan
--enable-row-security; validasi pemulihan berkunci memerlukan token svc-app valid.

## Sinkronisasi main sebelum penggabungan Modul A

Main 27aa9fa memuat scanner v1.2 dan amandemen docs/targets.md: baseline_1m
menjadi dataset benchmark utama; baseline_100k tetap titik skala terpisah.
Perubahan itu digabung tanpa konflik dan tanpa mengubah kontrak blob/profile v1.
Migrator pada penggabungan ini tetap hanya menerima pasangan 734/100k yang
sudah diuji. baseline_1m->protected_1m belum diimplementasikan/dijalankan; jangan
memakai hasil protected_100k sebagai pembanding before/after baseline_1m.
Ekstensi target 1M memerlukan perubahan allowlist, provisioning, guard count,
pengujian dan eksekusi migrasi tersendiri. Tidak membuat/mengubah dataset lokal
untuk keperluan merge. Integrasi Service App dan adapter benchmark protected
tetap mengikuti handoff A/B/C, terpisah dari penggabungan kode ini.

## Penyelesaian ekstensi 1M dan ukuran konfigurabel

Ekspektasi 734/100000/1000000 dan pasangan DB didefinisikan dalam
infra/database-targets.json, dibaca bersama oleh CLI, connection guard dan
provisioning. --expected-rows mengubah ekspektasi ukuran untuk pasangan yang
sudah diizinkan, bukan membuka database lain. Nilai harus integer non-negatif
dalam jangkauan bigint. Ekspektasi diperiksa pada snapshot source sebelum
pembuatan job/penulisan baris; count/fingerprint/checkpoint saat resume tetap
wajib cocok. Format enkripsi, AAD, normalisasi dan versi HMAC tidak berubah.

02_migration.sql meningkatkan CHECK lama ke tiga source tanpa menghapus progres.
TLS updater menambahkan baseline_1m/protected_1m dengan mengganti hanya blok HBA
lama yang persis dikenal dan mempertahankan tail autentikasi. Blok yang berubah
atau duplikat ditolak. Test nyata memverifikasi upgrade, rollback, penolakan
non-TLS pada lima DB dan pemeliharaan data; kedua baseline tetap source read-only.

Saat penyiapan ditemukan provenance profile lama bergantung byte LF/CRLF dari
checkout Windows. Loader kini memeriksa kedua identitas teks yang setara sebelum
membandingkan profile penuh terhadap input/kontrak. Fingerprint job baru memakai
profile LF kanonik; checkpoint legacy hanya diterima bila hash cocok dengan byte
LF/CRLF profile saat ini. Hash yang tersimpan pada job lama dipertahankan pada
report, bersama profile_canonical_sha256. Isi/input profile yang berubah tetap
ditolak. Test resume membuktikan UUID, ciphertext dan wrapped DEK lama tidak berubah.

Uji penuh memakai source 734, 1001 dan **1000000** record buatan sendiri, TLS
PostgreSQL 18/OpenBao 2.5.5, CLI 1M yang sesungguhnya dan token workload terpisah.
**28 pemeriksaan lulus**, termasuk seluruh row/field decrypt-and-compare,
NULL/REF/age_band, bidx, source/profile/checkpoint drift, ukuran eksplisit yang
berbeda dari default, atomic rollback, idempotensi, scope role, upgrade dan
revokasi. Source checksum seluruh fixture tetap sama. Semua container/volume uji
dibersihkan; tidak ada corpus panitia disalin ke fixture atau plaintext ke evidence.

Total kasus integrasi skala penuh **1456,21 detik** (24m16s), termasuk setup,
generation, kasus regresi, migrasi/validasi dan cleanup. Peak RSS Python yang
tersampel 377176064 byte (~359,7 MiB); minimum ruang host teramati 9935814656 byte
(~9,25 GiB). Ini observasi diagnostik fixture pada laptop ini, bukan angka
benchmark resmi, total RAM seluruh Docker, atau batas sumber daya semua dataset.
Summary uniqueness tetap membutuhkan RAM sebanding jumlah nilai lookup unik.

Test gabungan, dijalankan per suite: 243 unit/regresi A + 4 integrasi infra/crypto
+ 1 integrasi skala 1M + 53 benchmark/datagen/verify + 193 scanner + 243 Service
App = **737 passed, 3 skipped**. JUnit dan manifest ada di evidence/integration/;
file tests-1m-unit.xml dan tests-1m-quick.xml adalah subset tambahan, tidak dihitung
ganda. Skip/warning dependensi tetap dicatat. Verifikasi checksum/TLS source
734/100k development setelah uji juga PASS; database yang ada tidak diregenerate.

Dataset primer baseline_1m milik C dan pengukuran benchmark tidak dijalankan pada
uji ini. Setelah pull, pemilik laptop benchmark menjalankan prepare/check/run
terhadap baseline_1m yang sudah diterima di sana, dengan token yang TTL-nya cukup
dan metadata ukuran/populasi yang sama. Adapter protected dan integrasi B tetap
pekerjaan terpisah; keberhasilan migrator tidak diklaim sebagai kelulusan API.
