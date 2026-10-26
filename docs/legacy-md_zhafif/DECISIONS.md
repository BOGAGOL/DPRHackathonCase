# Keputusan implementasi

## 2026-10-23 — Scope dan lokasi
Gunakan checkout yang ditentukan pengguna. Scanner tetap di folder Task1 di luar aplikasi, tidak dijadikan dependency/API. Tidak melakukan publikasi web/dataset.

## 2026-10-23 — Database dan identitas
PostgreSQL mengikuti instruksi pengguna. Dua server/container dan network terpisah, baseline hanya profile lab. Synthetic PK stabil berdasarkan nomor urut sumber, bukan constraint asli. Dua field allowlist demo (`nama`, `ruangan`) plaintext; 27 kolom lain dipertahankan sebagai envelope terenkripsi per field di JSON. Seluruh 29 nilai, NULL dan leading zero dipertahankan. Public fields adalah kebijakan demo, perlu persetujuan pemilik data untuk deployment nyata.

## 2026-10-23 — Pencarian dan session
POST `/anggota/search/ktp` menggantikan GET agar nilai tidak masuk URL/access log. Normalisasi hanya strip whitespace luar, tanpa memaksakan NIK 16 digit. Blind index HMAC memakai secret terpisah. Cookie session opaque HttpOnly, hash token di DB; CSRF untuk login dan perubahan state; origin validation.

## 2026-10-23 — Kunci dan batas klaim
Local AES-256-GCM hanya development; versi envelope, nonce acak 96 bit, AAD record+field. Adapter Transit memakai HTTPS verified dan AAD; tidak mengekspor key. Transit deployment belum diuji. Metadata key Transit mengikuti ciphertext `vault:vN`; envelope version adalah format, bukan rotasi kunci Transit. Tidak ada fallback plaintext.

## 2026-10-23 — Pengujian
SQLite hanya untuk tes cepat policy/API/crypto, PostgreSQL tetap target deployment. Hasil Docker/PostgreSQL/browser/TLS dicatat terpisah. Tidak menandai semua fase DONE dari unit test.

## 2026-10-23 — Native PostgreSQL dan provisioning
Docker Engine tidak aktif, tetapi PostgreSQL 17 client/server tersedia. Buat dua cluster baru pada folder `.local` dan port 55432/55433, tidak mengubah instance lain. Pilih IPv4 eksplisit karena koneksi libpq `localhost` menunggu IPv6. Cluster/API/web dihentikan lewat launcher milik proyek, tanpa menyasar proses PostgreSQL lain. Secret file lokal adalah kemudahan lab, bukan kustodi produksi. Script configure/provision menolak overwrite.

## 2026-10-23 — Data sumber yang tidak valid tetap utuh
Parser menerima quoted strings, NULL dan numeric literals tanpa mengeksekusi dump. Nilai disimpan sebagai string/NULL. Form kontak meminta nilai pengganti saja dan hanya mengirim dirty fields, sehingga email dummy lama yang tidak lolos aturan form tidak menghalangi edit alamat. Backend memvalidasi nilai baru, bukan menormalisasi seluruh record secara diam-diam. Kesamaan parser diverifikasi independen terhadap parser Task1 pada 734 record.

## 2026-10-23 — Benchmark terukur dan recovery
Bandingkan DB business read/write dengan output kontak yang sama, seed dan concurrency sama, tiga pengulangan urutan bergantian. Snapshot data dikembalikan setelah benchmark. Generator 10.000 record seluruhnya baru, memakai database baru. Metrik CPU cluster adalah proses native PostgreSQL, RAM sum working sets memiliki shared-memory double counting. HTTP/TLS/auth/audit tidak masuk pengukuran performa ini. Backup memakai format custom pg_dump dan AES-GCM key independen; restore selalu pada DB baru, tidak downgrade/drop schema atau overwrite database aktif.

## 2026-10-23 — Deployment guard dan batas izin
Konfigurasi non-development menuntut HTTPS origin, Secure cookie, provider selain local, dan PostgreSQL verify-full/root CA. Ini guard konfigurasi, bukan bukti TLS live. Admin permission manager dapat memberikan izin eksplisit kepada staff; pemisahan approver dua orang belum ada. `app_user` hanya mendapat sequence yang dibutuhkan, audit INSERT/SELECT tanpa UPDATE/DELETE; backup masih memakai owner lab, belum identity backup produksi.
