# Keputusan tahap 5

## Integrasi A/B recovery — 28 Oktober 2026

Pengguna mengizinkan perubahan A dan B dalam sesi ini karena pemilik B berhalangan.
Backup/manifest v1 menerima tepat layout A lima tabel atau A+B tujuh tabel; subset B
dan tabel tambahan lain tetap ditolak. Seluruh row count berada di payload HMAC.
Arsip lima tabel lama tetap dapat dipulihkan sebagai data, tanpa klaim akun/sesi B tersedia.

Layout B memerlukan ownership schema_owner, grant minimum (termasuk tidak ada grant
kolom tersembunyi/PUBLIC), serta service_legacy_id_seq yang tidak cycle dan next value
di atas seluruh legacy_row_id. B setup menambah SELECT sequence untuk backup_user;
operator existing perlu menjalankan ulang setup B yang idempoten, tanpa reset sequence.
Drill retensi memakai allocator B pada clone miliknya agar insert sintetis tidak
membuat sequence tertinggal. State sequence tidak dianggap snapshot MVCC; restore
memeriksa kelayakan next value, bukan menyamakan state racy dengan pengukuran count.

Restore menolak sebelum CREATE DB bila HBA belum menolak plaintext untuk target
dpr_restore_<32 hex>. Jalankan updater TLS terbaru terlebih dahulu. Setelah validasi
data/schema, marker dpr-service-restore-v1:<artifact UUID> dan grant CONNECT dipublish
dalam transaksi yang sama. Marker merupakan provenance operator DB, bukan tanda tangan
kriptografi dan bukan pertahanan terhadap operator superuser yang berbahaya. Hash/HMAC/
AEAD arsip tetap diperiksa terpisah sebelum alokasi target. Guard cleanup mengikuti
marker baru, nama dan OID; target/data existing tidak ditimpa.

Mode tanpa OpenBao memulihkan ciphertext dan kontrol B; startup/dekripsi layanan tetap
memerlukan identitas svc-app dan key plane yang benar. Akun, scope, binding dan sesi
dipulihkan beserta TTL sesi yang sudah ada. Mengakhiri sesi existing saat cutover adalah
keputusan operator terpisah; tidak diam-diam mengubah row count manifest. Uji HTTPS
backend memiliki evidence tersendiri, bukan diperoleh dari smoke_decrypt saja.

Verifikasi setelah WSL pulih, 28 Oktober: empat test integrasi lulus. TLS mencatat
90 pemeriksaan, backup lima tabel 15, dan recovery tujuh tabel 33. Akun/sesi existing,
enam peran, pembatasan record/FIN, pencarian, update bidx/kontak, insert ID berikutnya,
key identity fail closed, tamper dan retention terbukti melalui HTTPS backend nyata.
Fixture berisi 17 record buatan sendiri; container/volume sementara dibersihkan.
Evidence: `evidence/backup/service-recovery-integration.json` dan
`evidence/recovery/verification.json`. Source yang diuji `5214829`; bukan benchmark
resmi atau klaim pengujian database tim 734/100k/1M. Tidak ada perubahan source
implementasi setelah run ini; pembaruan berikutnya hanya dokumentasi/evidence.

## Adaptasi referensi dan format

Referensi dibaca: `docs/reference/onno-code/data-leak-proof-postgresql/scripts/backup.sh`
dan `restore.sh`. Referensi menyimpan dump plaintext dan restore melakukan `--clean`
ke database yang diberikan. Implementasi ini memakai pipe pg_dump → AES-GCM dan
AES-GCM → pg_restore ke database baru, tanpa file dump plaintext.

Memilih AES-256-GCM berbingkai agar berjalan dengan dependency cryptography yang
sudah dipakai toolkit di Windows, tanpa instalasi binary age. Kunci master backup
32 byte terpisah dari DEK/KEK data dan kunci HMAC manifest. HKDF-SHA256 menurunkan
kunci tiap artifact dengan salt UUIDv4 dan info `dpr|backup|v1`.

Format biner v1: header `DPRBAK01` (8) + artifact UUID (16) + ukuran chunk big-endian
(4, tetap 1 MiB). Setiap frame: panjang plaintext uint32 + nonce acak CSPRNG (12)
+ ciphertext + tag (16). AAD = header + nomor frame uint64 + panjang uint32.
Frame terakhir memiliki plaintext kosong dan tag terautentikasi; wajib EOF sesudahnya.
Pertukaran urutan, truncation, trailing bytes, header/nonce/tag rusak gagal tertutup.
Plaintext tiap frame dilepas hanya setelah tag valid. Memori O(1 MiB), tidak O(jumlah record).
Ini format **backup**, tidak mengganti blob/AAD field kontrak v1.

Manifest: JSON canonical sort_keys, separators `,`/`:`, ASCII, tanpa NaN;
HMAC-SHA256 atas `payload`, disimpan bersama payload. Payload memuat UUID, waktu UTC,
deadline, SHA256/ukuran **encrypted artifact**, count per tabel dan anggota, database
sumber, algoritma/version/key ids, role, snapshot-consistent dan waktu backup.
Fingerprint key id berasal dari kunci berentropi tinggi, tidak berisi kuncinya.
Setiap artifact/manifest dibuat eksklusif; direktori privat di luar checkout.

## Snapshot, TLS, role, restore

Count dan pg_dump memakai satu snapshot REPEATABLE READ READ ONLY melalui
`pg_export_snapshot()` / `--snapshot`. `--enable-row-security` diperlukan karena
backup_user NOBYPASSRLS; policy backup tahap 3 mengizinkan seluruh baris.
Custom dump memakai COPY; restore dijalankan operator bootstrap/superuser karena
COPY FROM tidak mendukung RLS pada role terbatas. Tidak menambah hak backup_user.

Tools PG18 dipanggil lewat Docker exec container yang ada, host internal 127.0.0.1:5432,
TLS verify-full dengan CA publik. Password lewat nama environment `--env PGPASSWORD`,
bukan nilai argv. Probe random application_name mengikat container ke sesi TLS
Python yang sama; tidak mengandalkan nama container semata.
stderr subprocess tidak ditampilkan/disimpan karena bisa memuat data SQL/row.

Restore memverifikasi HMAC, SHA/ukuran, dan **seluruh tag frame** sebelum CREATE DB;
kemudian decrypt ulang streaming dari file descriptor yang sama. pg_restore memakai
`--single-transaction --exit-on-error`, tanpa --clean, --create, --no-owner atau --no-acl.
Owner schema_owner, grants, default privileges dan FORCE RLS dipertahankan.
Runtime CONNECT diberikan setelah validasi count/security/smoke berhasil.
Restore gagal dibersihkan hanya bila nama, OID dan comment provenance cocok dengan
DB yang dibuat invocation tersebut. Database sumber/target existing tidak dihapus.

Verifikasi memakai lima tabel public kontrak saat ini: anggota_protected, app_users,
access_scope, audit_log, migration_jobs. Tabel tambahan modul lain membuat backup
menolak sampai cakupan dan hitung validasinya disepakati; jangan diam-diam melewatkan.
Token OpenBao hanya diperlukan mode `--with-openbao` / retention. Smoke mengautentikasi
semua field AEAD sampel (default 16 anggota, kedua domain) tanpa menulis plaintext.
Keberhasilan ini membuktikan pemulihan DB dan kemampuan dekripsi; integrasi HTTP
Service App B dan alih koneksi layanan tetap perlu diuji bersama B.

## Retensi, pemulihan kunci dan batas

Retensi: restore clone → sisipkan **anggota sintetis baru** yang dienkripsi melalui
toolkit/Bao → backup kontrol → restore memastikan ada → hapus UUID+legacy id tersebut
di clone → backup baru → restore memastikan tidak ada dan smoke dekripsi tetap jalan.
Database sumber tidak menerima DML. Tiga DB scratch dibersihkan berdasarkan identitas.
Backup kontrol lama tetap memuat anggota sampai expiry. Deadline adalah metadata
retensi terautentikasi; implementasi ini tidak menghapus arsip kedaluwarsa otomatis
dan tidak mengklaim secure erase SSD/WAL/snapshot. Operator menjalankan penghapusan
arsip lama sesuai kebijakan media setelah mempertimbangkan kewajiban retensi.

Kehilangan salah satu backup key/HMAC key menghalangi restore. Kehilangan key plane
OpenBao menghalangi dekripsi field walaupun DB restore berhasil. Simpan salinan
pemulihan **terpisah** dari arsip, akses dibatasi; DPAPI lokal bukan escrow lintas laptop.
Untuk DR lintas mesin, operator perlu escrow kunci backup, material pemulihan OpenBao,
serta bootstrap role dan password baru. Jangan taruh material itu di Git/evidence/chat.
Dump SQL terautentikasi tetap harus berasal dari produsen backup tepercaya: operator
restore memiliki kemampuan DDL; kompromi kunci backup/HMAC bukan ancaman yang ditutup
oleh HMAC. Data+key plane dikuasai bersama berada di luar jaminan kerahasiaan.

Rujukan perilaku tools: PostgreSQL 18
[pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html) dan
[pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html).
Streaming stdin tidak memakai --jobs (parallel restore memerlukan file biasa).

## Hasil lokal 27 Oktober 2026

Data yang sudah dimigrasikan diuji tanpa menulis ke sumber. Dua mode restore lulus;
setiap restore menghitung seluruh tabel, memeriksa owner/ACL/RLS dan mode OpenBao
mendekripsi 16 anggota (392 field non-NULL) di memori. DB hasil verification drill
dibersihkan sesudah laporan disimpan; CLI restore biasa mempertahankan DB.

| Sumber | Baris | Encrypted bytes | Backup detik | Restore tanpa Bao | Restore dengan Bao |
|---|---:|---:|---:|---:|---:|
| protected_734 | 734 | 1,244,857 | 1.484788 | 2.158697 | 1.525642 |
| protected_100k | 100,000 | 165,999,475 | 11.376413 | 18.875632 | 16.415305 |

Ini satu engineering drill per dataset, **bukan benchmark resmi median 3 run**.
Evidence: `evidence/backup/local-protected_734.json`, `local-protected_100k.json`,
`restore-report.json`, `tamper.json`, `retention.json`, `source-preservation.json`.
Tamper 1 byte ditolak sebelum CREATE DB. Retensi clone 735 → 734 lulus; sumber
protected tetap utuh. Hash dataset postgres dan baseline_100k sebelum/sesudah sama.
Token svc-app khusus verifikasi ber-TTL 1 jam dicabut pada akhir drill; backup tidak
memakai token itu. Tidak ada root/unseal/DEK/backup key dalam evidence.

`protected_1m` didukung oleh CLI dan pipeline tanpa asumsi jumlah record, tetapi
belum diuji backup lokal karena dataset tersebut belum ada di laptop ini. Rekan
benchmark menjalankannya setelah migrasi 1m pada laptopnya sendiri. Backup DB hasil
migrasi rekan membutuhkan key plane rekan untuk mode dekripsi; key plane laptop
lain tidak dapat membuka wrapped DEK tersebut.

Windows lokal tidak menyediakan cmdlet ConvertTo-SecureString di proses helper
PowerShell yang dipakai. Helper membuat SecureString lewat .NET seperti helper
kredensial tahap sebelumnya; roundtrip DPAPI nyata diuji, bukan mock saja.
