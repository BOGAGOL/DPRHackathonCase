# 4. Implementasi Modul A, migrasi dan rotasi

## Peta kode yang benar

Runtime aktif adalah app/, infra/, toolkit/dprcrypto/, policy/, migration/,
sql/protected/, sql/roles/, scripts/backup/, scanner/, datagen/, benchmark/, verify/.
Prototipe PG17/apps/infrastructure telah dipisahkan pada branch perapian; jangan
mencampur diagram/env/skema lama dengan implementasi ini. Nomor tahap berikut
mengikuti pekerjaan Modul A, bukan enam tantangan panitia.

| Tahap | Implementasi | Pengujian/hasil dan batas |
|---|---|---|
| A1 Infra | PostgreSQL 18, Bao 2.5.5 TLS, CA lokal, bootstrap/3 share threshold 2, Transit/policy/token TTL | Probe TLS/associated_data/ACL; bukan PKI/HA produksi |
| A2 Toolkit | codec, keys, bidx, openbao, masking, shared vectors | Round-trip, 1-bit tamper, AAD swap, nonce, batch/cache/policy/CA/error; bukan bukti semua artefak bocor |
| A3 Profile/schema/roles | Assessment+override, 25 _ct, REF/bidx, akun/scope/audit, least privilege/RLS | Profile traceable, role negative tests, A5 aggregate-only kemudian ditambahkan |
| A4 Migrasi | Database baru, snapshot/progress, UUID/DEK, enkripsi batch, full validation, revokasi | 734/100k/1M punya bukti per target/lingkungan |
| A5 Backup/restore | Stream pg_dump ke framed GCM, HMAC manifest, dua mode, tamper/retention | Lab/data dan recovery layanan berbeda, dibahas terpisah |
| A6 Rotasi | pii-kek rotate lalu rewrap wrapper, checkpoint/CAS, decrypt comparison | 100.734 wrapper PII versi 2 pada lab Alby; bukan bukti rotasi 1M/semua VM |

## Skema dan identitas

Tabel anggota_protected: UUIDv4 anggota_id primary key, legacy_row_id unique,
protection_version, dua wrapped DEK, 25 bytea `<kolom>_ct`, tiga bytea bidx,
empat REF, age_band dan timestamp. Bidx diindeks untuk lookup. UUID internal
terikat AAD; API B saat ini menggunakan business id legacy_row_id yang disajikan
sebagai string/integer route, bukan memindahkan UUID itu menjadi id URL.

Tabel lain: access_scope(principal, anggota_id, permission) adalah data kebijakan
sintetis, bukan atribut kewenangan asli yang ditemukan di dump; audit_log adalah
metadata operasi; migration_jobs mengendalikan progress. A menyediakan app_users,
B menambah users/sessions serta control/marker sesuai bootstrap layanan. Jangan
menyebut app_users dan users dua nama alternatif tabel yang otomatis sama.

age_band dihitung berdasarkan usia tahun penuh pada tanggal acuan 2026-10-01,
kelompok 10 tahun, NULL tetap NULL. Ini bukan age band dinamis menurut tanggal
penulisan laporan atau usia hari ini.

## Role minimum dan RLS

schema_owner NOLOGIN; runtime tidak memakai owner/superuser. app_user
NOSUPERUSER/NOBYPASSRLS dan tanpa DDL; analyst_user hanya aggregate A5;
auditor_user audit metadata; backup_user SELECT minimum untuk dump; admin_user
administrasi akun/scope terbatas; migration_user sementara; scanner_user read-only.
Password SQL berasal variabel psql/env privat. CREATE public dicabut dari PUBLIC,
default privileges diketatkan, GRANT per objek/fungsi disesuaikan per fungsi.

RLS anggota_protected ENABLE+FORCE; scope transaksi memakai
current_setting('app.principal',true), diisi SET LOCAL/set_config dalam transaksi.
Tanpa scope tidak mendapat record. RLS tetap mempunyai policy khusus untuk
owner/migrasi/backup/scanner yang sah. Karena app_user dapat mengganti setting,
RLS adalah defense-in-depth terhadap kesalahan query, bukan batas identitas
kuat terhadap pencuri credential role tersebut.

## Algoritme migrasi

1. prepare admin membuat target baru/menyiapkan objek dan role yang cocok; tidak
   DROP/TRUNCATE source. Target berisi data asing/tanpa checkpoint cocok ditolak.
2. check memverifikasi dependency, pasangan source-target allowlist, jumlah source,
   identitas DB/TLS, profile dan policy token. Source query read-only.
3. Job merekam snapshot/hash source, hash canonical profile dan progress. Batch
   default 1000 (1–1000); RPC crypto dibagi maksimal 100. Perubahan source/profile
   saat resume ditolak, bukan ditafsirkan sebagai job baru yang boleh overwrite.
4. Tiap record: UUIDv4, DEK_PII/FIN CSPRNG baru, Transit wrap, konversi nilai,
   encrypt setiap AEAD dengan AAD, HMAC tiga kolom, REF/age_band, INSERT.
5. Row dan checkpoint commit bersama. Batch gagal tidak memajukan checkpoint.
   Batch lama yang sudah commit tidak diacak ulang; legacy_row_id mencegah duplikat.
6. Setelah semua baris: baca kembali hasil target dan decrypt-and-compare **semua
   field/semua record**, termasuk NULL/REF/age_band, hitung ulang bidx, count dan
   uniqueness bidx jika sumber ternormalisasi unik. Tidak mencetak nilai pembanding.
7. Sukses mencabut svc-migration secara default; validator memakai svc-app terpisah.
   migration_user ditutup NOLOGIN oleh operator pada penutupan sesi. Role DB
   NOLOGIN dan token revocation merupakan dua kontrol berbeda.

Pause menggunakan --max-batches, resume dengan perintah/source/profile sama.
Token expired perlu token baru terbatas; tidak auto-renew. Default expected_rows
734/100k/1M menjaga dataset terpotong tidak dianggap lengkap. --expected-rows
memungkinkan jumlah lain pada pasangan target yang diizinkan: kemampuan jumlah
fleksibel tidak berarti bebas target arbitrary atau memodifikasi source.

## Hasil migrasi yang dapat ditulis

protected_734: 734 baris tervalidasi pada lab development Alby. protected_100k:
100.000 baris tervalidasi; ada bukti development dan laptop benchmark berbeda.
protected_1m: 1.000.000 baris, all_rows_all_fields, migration token revoked,
migration_user NOLOGIN pada laptop benchmark. Gunakan bukti per target, bukan
validation.json generik yang dapat tertimpa operasi terakhir.

Durasi laptop 100k tercatat 192,562236 s termasuk validasi penuh dan pencabutan token;
prepare 8,528233 s terpisah. Jangan mencampur angka ini dengan benchmark request,
estimasi linear 1M lama, atau timer live lab lain. Checksum source/migrated data
dibandingkan secara semantik; ciphertext acak tidak diharapkan byte-identik.

## Rotasi pii-kek

Rotasi Transit menaikkan versi KEK, lalu rewrap mengubah wrapper DEK tanpa
mendekripsi field bisnis/menulis DEK. Ciphertext field dan AAD tidak perlu berubah.
key-operator tidak login DB; writer memakai fungsi/ACL terbatas. Update batch
compare-and-swap mencegah menimpa wrapper yang berubah bersamaan. Advisory lock
melindungi coordinator pada DB tersebut, bukan semua aplikasi/cluster lain.

Run sempat gagal/terhenti lalu dilanjutkan dengan **target versi yang sama**.
Bukti akhir lab: 100.000 + 734 wrapper PII semula v1 menjadi v2, validasi semua
PII/FIN tetap terbaca. Tidak mengubah minimum decryption version, tidak menghancurkan
versi lama, tidak merotasi FIN/search otomatis. Backup sebelum rotasi masih dapat
dipulihkan selama versi kunci lama tersedia. Jangan mengulang rotate tanpa
memeriksa checkpoint karena bisa membuat versi tambahan yang tidak direncanakan.
