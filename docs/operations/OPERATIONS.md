# Operasional, retensi dan pemulihan

Status: prosedur awal untuk prototipe; perlu persetujuan operator instansi dan
drill key-plane lintas mesin sebelum klaim disaster recovery penuh.

## Urutan penerapan berbasis risiko

1. Inventaris schema/kolom, kebutuhan akses, ketergantungan dan data turunan.
2. Sahkan klasifikasi/risiko dan protection profile; simpan alasan override scanner.
3. Siapkan CA/TLS, key plane, role minimum dan custody, tanpa credential di repo.
4. Rekam baseline sebelum perubahan; koordinasikan semua mutasi dengan pemiliknya.
5. Migrasikan ke target baru dan validasi seluruh nilai/NULL/bidx/age_band.
6. Provision akun/scope, uji otorisasi dan A5, lalu cutover aplikasi dengan rollback.
7. Backup terenkripsi, restore layanan, retensi/pemusnahan, audit dan rotasi.
8. Ukur overhead/risiko residual, tulis keterbatasan dan jadwalkan review ulang.

## Custody dan restart

Unseal manual memakai threshold dua dari tiga share. Pisahkan kustodian dan salinan
pemulihan dari database/arsip. Root token hanya bootstrap/recovery operator; aplikasi
memakai svc-app TTL terbatas. Setelah restart stack existing, start container yang
sama dan unseal; jangan init ulang. Refresh token dan CA/cert mengikuti runbook,
bukan dengan mematikan verifikasi TLS. Rahasia DPAPI Windows tidak otomatis portable
ke Ubuntu. Jangan kirim key/token/password/share ke chat, Git atau evidence.

## Pemulihan data dan key plane

Restore data: verifikasi HMAC manifest, SHA256 dan autentikasi seluruh frame,
buat database restore baru, terapkan/hardening ACL A5, validasi count dan decrypt
smoke bila capability tersedia, baru buka CONNECT dan cutover terkontrol.
Tanpa OpenBao, field tetap ciphertext. Pemulihan HTTP/browser telah diuji pada
lab 17 record; ini bukan recovery seluruh VM atau bukti semua dataset produksi.

Pemulihan key plane memerlukan salinan storage OpenBao yang konsisten serta material
unseal/recovery yang cocok, CA/cert dan credential privat; nama `pii-kek` yang sama
pada OpenBao baru tidak menghasilkan kunci lama. Storage saat ini backend file,
bukan Raft: jangan memakai resep snapshot Raft tanpa perubahan arsitektur.
Operator perlu menentukan cara backup konsisten/offline volume, escrow lintas mesin,
uji restore ke stack terisolasi, dan pencabutan credential darurat. Detail drill
tersebut belum diuji lengkap; catat sebagai rencana, bukan PASS.

## Retensi dan pemusnahan

Backup default mempunyai deadline 30 hari yang diautentikasi manifest; parameter
retensi dapat dipilih sesuai kebutuhan/kewajiban yang disahkan instansi. Penanggung
jawab backup harus mereview daftar artefak, kebutuhan penahanan, dan salinan mirror,
lalu mencatat penghapusan arsip+manifest yang telah kedaluwarsa. Tidak ada purge
otomatis atau klaim secure erase SSD/WAL/snapshot pada implementasi ini.

Drill deletion hanya menghapus anggota sintetis pada clone milik test, membuat
backup baru, lalu membuktikan anggota tidak muncul lagi. Backup lama dapat tetap
memuatnya sampai expiry. Jangan menghapus database source/baseline untuk membuktikan
retensi. Penghapusan file di satu lokasi bukan bukti seluruh salinan telah dimusnahkan.

## Resource dan biaya yang perlu dihitung

Catat mesin/OS/CPU/RAM/disk, storage DB sebelum/sesudah, koneksi dan request Transit,
ukuran/durasi backup/restore, ruang WAL serta salinan restore. Retention drill dapat
memerlukan beberapa salinan DB; pilih dataset kecil pada lab dengan ruang terbatas.
Biaya instansi mencakup compute/storage VM, backup terpisah, sertifikat/operasi,
pengelolaan kustodian, review/audit dan waktu pemulihan. Tidak ada estimasi rupiah
atau kapasitas produksi yang telah divalidasi pada prototipe ini.

## Rollback

Kegagalan upgrade A5 menggulung transaksi. Bila SQL A5 telah sukses tetapi aplikasi
belum siap, pertahankan maintenance analytics; jangan mengembalikan raw SELECT.
Kegagalan migrasi dilanjutkan dengan checkpoint/profile yang cocok, bukan menimpa
source. Cutover data dibatalkan dengan kembali ke target/service yang diverifikasi
operator; tetap pertahankan kunci/versi yang diperlukan backup lama. Detail:
[migrasi](../../migration/README.md), [recovery B](../../app/docs/RECOVERY.md),
[rotasi](../../infra/rotation/README.md), [A5](../../infra/protected/ANALYST_SUPPRESSION.md).
