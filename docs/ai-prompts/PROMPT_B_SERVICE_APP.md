# Prompt Modul B: Service Application + Access Control (pemilik: anggota tim CRUD)

Baca `AGENTS.md` dan `docs/contracts/CONTRACT.md` terlebih dahulu. Folder milikmu: `app/`.
Jika kode CRUD sudah ada di `app/`, pertahankan stack-nya dan refactor sesuai tugas ini.

## Tujuan
Membuktikan Tantangan 4 soal: kontrol backend (autentikasi, otorisasi peran dan per record, query
berparameter, validasi input, least privilege, rahasia, audit) dan frontend (hanya data yang
diizinkan yang dikirim ke browser; periksa respons API, storage browser, sesi, cache, XSS).
"Data yang disembunyikan di tampilan tetapi tetap dikirim ke browser belum terlindungi."

## Dua mode aplikasi dari satu kode
- `MODE=plain`: membaca `baseline_100k` (plaintext). Dipakai sebagai baseline benchmark API.
- `MODE=protected`: membaca `protected_100k` / `protected_734` lewat crypto adapter.
Endpoint dan bentuk respons SAMA di kedua mode supaya benchmark adil.

## Crypto
- Jika backend Python: impor paket `toolkit/dprcrypto` (modul A). Jangan menulis kripto sendiri.
- Jika backend bukan Python: implementasi decrypt/encrypt/bidx sesuai kontrak bagian 5-7 dengan
  library standar bahasa tersebut, dan WAJIB lulus `docs/contracts/test_vectors.json`. Unwrap DEK
  lewat OpenBao HTTP API (TLS verify).
- Gagal dekripsi -> HTTP 500 generik + audit event, tanpa plaintext/fallback.

## Peran aplikasi (akun demo sintetis, password Argon2id)
| Peran | Lihat daftar | Detail | KTP | Rekening/NPWP | Agama | Edit kontak |
|---|---|---|---|---|---|---|
| `operator` | nama masked | nama, kontak masked | masked | tidak | tidak | ya (handphone, email) |
| `privileged_officer` | nama penuh | penuh kecuali finance | penuh | tidak | penuh | ya |
| `finance_officer` | nama masked | minimal | masked | penuh | tidak | tidak |
| `analyst` | tidak ada akses record; hanya endpoint agregat dari `analyst_view` (via role DB `analyst_user`) |
| `auditor` | tidak ada akses data anggota; hanya log audit (role DB `auditor_user`) |
| `anggota` | hanya record miliknya sendiri (dicocokkan lewat `pengguna_bidx`) | masked kecuali miliknya | ... |
Matriks final dicatat di `app/ACCESS_MATRIX.md` dan diterapkan di satu tempat (policy module).

## Endpoint minimum
- `POST /auth/login`, `POST /auth/logout`
- `GET /anggota?page=` (daftar, 50 per halaman)
- `GET /anggota/{anggota_id}` (detail, field sesuai peran)
- `GET /anggota/search?no_ktp=` dan `?email=` (lewat blind index)
- `PATCH /anggota/{anggota_id}/kontak` (handphone/email; re-encrypt + update bidx)
- `POST /anggota` (insert, untuk benchmark tulis)
- `GET /analytics/summary` (analyst; agregat dari analyst_view)
- `GET /audit` (auditor)

## Aturan implementasi
1. Otorisasi object-level di setiap endpoint (deny by default). Uji IDOR: peran `anggota` meminta
   id orang lain -> 403/404.
2. Field-level: query hanya kolom yang dibutuhkan, dekripsi hanya field yang diizinkan, bentuk DTO
   eksplisit per peran. Dilarang serialize seluruh row lalu disaring di frontend.
3. Daftar: batch unwrap DEK untuk satu halaman, decrypt hanya kolom yang ditampilkan.
4. Koneksi DB memakai role `app_user` dengan `sslmode=verify-full`. Set `SET LOCAL app.principal`
   per transaksi untuk RLS.
5. Sesi: cookie `HttpOnly`, `Secure`, `SameSite=Strict`, masa berlaku pendek; tidak menyimpan token
   atau data pribadi di `localStorage`/`sessionStorage`.
6. Header: `Cache-Control: no-store` untuk respons berisi data pribadi, CSP ketat (tanpa inline
   script), `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors 'none'`.
7. Frontend: render teks dengan escaping default; dilarang `innerHTML`/`dangerouslySetInnerHTML`
   untuk data. CSRF protection untuk request yang mengubah data.
8. Validasi input (format NIK/email/telepon), rate limit login.
9. Audit: setiap akses detail dan dekripsi dicatat ke `audit_log` (actor, peran, aksi, anggota_id,
   kelas field, keputusan, request_id). TANPA nilai data.
10. Log aplikasi tidak memuat body request, query string berisi NIK/email, token, atau password.
11. HTTPS untuk browser (sertifikat lokal dari modul A).

## Test wajib (hasil mesin ke `evidence/access-control/`)
- Matriks peran x endpoint x field: respons hanya berisi field yang diizinkan (cek JSON mentah).
- IDOR/BOLA ditolak; peran analyst/auditor tidak bisa memanggil endpoint detail.
- SQL injection payload pada pencarian tidak mengembalikan data lain.
- XSS: nilai berisi `<script>` tampil sebagai teks (test komponen atau e2e sederhana).
- Header keamanan dan atribut cookie ada.
- Gagal dekripsi (ciphertext ditukar oleh test) -> 500 generik, tidak ada plaintext.
- Mode plain dan protected memberi hasil yang sama untuk peran berwenang (uji kebenaran).

## Definisi selesai
Selasa malam: MODE=plain berjalan penuh (untuk baseline API). Rabu siang: MODE=protected berjalan
dengan semua test di atas. `app/README.md` berisi cara menjalankan di PowerShell.
