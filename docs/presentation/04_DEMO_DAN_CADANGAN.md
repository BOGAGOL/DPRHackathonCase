# 4. Demo, privasi dan skenario cadangan

**Status: rencana demo, bukan sesi demo yang sudah direkam/dijalankan pada tugas ini.**
Tidak ada akun, password, cookie, key, token, alamat credential atau isi record
yang disimpan dalam paket presentasi. Deployment yang pernah diuji tidak otomatis
berarti siap untuk ditampilkan sekarang tanpa preflight operator.

## Ruang demo dan batas izin

Pilihan yang paling mudah dikendalikan adalah lab/clone khusus dengan record
sintetis **buatan tim sendiri**, akun scope yang disiapkan, dan TLS yang sah.
Evidence lab17 record sudah ada; itu bukan pernyataan proses lab masih hidup.
Operator perlu menyiapkan ulang lingkungan terisolasi sebelum presentasi.

Jika memakai VM existing protected_734, dataset panitia tetap mempunyai batas
publikasi. Jangan membuka detail yang mengirim nama/identifier/keuangan lengkap.
Pilih agregat/hasil termasking yang telah direview. Finance memang mendapat nilai
FIN lengkap menurut hak; jangan menampilkan responsnya ke proyektor hanya karena
akun sah. Operator detail membuka nama, sehingga jangan menganggap semua detail
otomatis aman. Perbedaan masking runtime/toolkit tetap berlaku.

Tidak ada reset/provisioning, insert/delete anggota, migrasi, key rotation,
unseal, revokasi token atau restore berat pada database existing saat demo.
Login/logout normal tetap menulis metadata sesi/audit; “read-only anggota” bukan
tidak ada perubahan metadata sama sekali. Jangan mengakses laptop benchmark Delf.

## Rundown240 detik di dalam S05

| Detik | Aksi yang disiapkan | Hasil yang harus tampak | Cadangan bila tidak siap |
|---|---|---|---|
| 0–15 | Buka browser/demo yang sudah preflight | HTTPS sah, layar bersih tanpa terminal/env/credential | Jelaskan ini akan memakai evidence tersimpan |
| 15–50 | Operator membuka daftar, bukan detail berisi sumber lengkap | Nama termasking, respons sesuai allowlist | Ilustrasi berlabel atau screenshot fixture yang benar-benar direkam dan direview |
| 50–90 | Akun anggota fixture sendiri vs record fixture lain | Record sendiri sah, record asing ditolak, tanpa membuka identitas sumber | Tunjukkan nama checks terkait pada laporan lab, bukan response anggota |
| 90–150 | Analyst membuka summary/filter marginal | count>=5, total=null, tanpa baris per record; cohort filter ditolak | Bukti SQL A5 dan lab nyata yang sudah ada |
| 150–220 | Buka ringkasan restore/tamper yang sudah disanitasi | Backup rusak ditolak; dua mode restore dan scope lab dijelaskan | Slide S05 dengan kutipan evidence, berlabel “hasil pengujian sebelumnya” |
| 220–240 | Logout dan kembali ke presentasi | Sesi berakhir, tidak ada secret di layar | Tutup demo, lanjut S06 |

Jangan membuka developer tools bagian headers/cookies atau shell yang pernah
memuat environment privat. Jika ingin menunjukkan raw JSON, gunakan fixture dan
respons allowlist yang direview terlebih dahulu; jangan memperlihatkan request
header atau network trace mentah. Jangan memakai browser dengan password manager,
autofill, notifikasi pribadi atau akun lain yang terlihat.

## Preflight operator sebelum hari presentasi

1. Tentukan lingkungan dan pemiliknya; verifikasi tidak ada benchmark aktif dan
   tidak akan menyentuh sumber panitia atau instance anggota lain.
2. Siapkan fixture, record assignment, akun dan hak yang tepat lewat prosedur
   berizin. Langkah setup bukan bagian live demo dan tidak dilakukan tugas ini.
3. Periksa initialized/unsealed Bao tanpa membuka recovery material; CA/hostname
   TLS benar, token memiliki TTL cukup, service siap dan app cache OFF.
4. Periksa scope/field/A5 pada kode yang benar-benar terpasang. Catat commit dan
   waktu secara privat/metadata aman; jangan menganggap metadata lab lama sebagai
   bukti setiap konfigurasi VM sekarang.
5. Latih semua langkah, urutan akun, logout, dan waktu. Login dilakukan privat
   sebelum proyeksi bila memungkinkan; tidak menaruh akun/password di slide/notes.
6. Rekam cadangan hanya setelah persetujuan tim dan review setiap frame serta
   audio/metadata. **Video/screenshot belum dibuat oleh paket ini.**
7. Siapkan laporan checks lokal dan deck agar demo tetap dapat dijelaskan tanpa
   internet. Labeli rekaman/evidence sebagai rekaman/hasil sebelumnya.

## Aturan gagal yang sederhana

Jika readiness/TLS/token/akun gagal, jangan mematikan verifikasi TLS, memberi
superuser, mengulang init atau mengganti root token. Setelah satu percobaan
singkat, gunakan evidence yang telah direview. Sisihkan sisa waktu untuk dampak
kinerja dan penerapan. Kesalahan diakui sesuai scope; tidak memalsukan UI sukses.

Kalimat fallback: “Layanan demo saat ini tidak siap, jadi kami menunjukkan hasil
pengujian sebelumnya. Bukti ini berasal dari lab17 record dengan PG 18/OpenBao TLS,
bukan operasi live barusan. Berikut pemeriksaan akses dan restore yang tercatat.”

## Yang dapat ditampilkan dari evidence

- SQL A5: analyst ditolak membaca raw table/view dan kelompok1–4 tidak dirilis.
- Lab 143 checks: record/field, HTTPS/TLS negative, API/Chrome dan recovery pada17 fixture.
- Web 100 checks: enam akun existing, scope web read-only anggota; tanpa SSH Alby.
- Operator VM: satu guarded reset dan65 smoke; bukan full pentest atau DR key-plane.
- Backup tamper: satu byte diubah pada salinan uji lalu restore ditolak sebelum
  DB dibuat; jangan mengubah arsip operasional hanya untuk demonstrasi.

Masing-masing bukti mempunyai waktu/lingkungan sendiri. Menampilkan laporan bukan
berarti menjalankan ulang test, dan bukan alasan mengekspor source dataset ke slide.
