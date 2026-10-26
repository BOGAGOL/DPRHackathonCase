# Skenario demo juri

Jalankan README dan baca credential lokal secara privat. Jangan tampilkan file password, raw SQL, token cookie, field key atau plaintext identitas lengkap pada proyektor. Empat akun demo: viewer, operator, staff, admin; username ada di file lokal. Dataset hanya sintetis.

Demo lima menit:

1. Login viewer: dashboard menampilkan count 734, direktori hanya nama/ruangan, profil tidak berisi kontak atau rekening. Perlihatkan allowlist respons tanpa menampilkan nilai sensitif.
2. Login operator: count assignment 12, halaman berikutnya bekerja. Profil hanya kontak termasking; form update meminta nilai pengganti. ID 734 ditolak di API meskipun ID di URL diubah. Admin UI tersembunyi dan API audit juga menolak.
3. Login staff: assignment 36, pencarian nomor KTP tepat dari fixture privat mengembalikan anggota yang ditugaskan. Tidak memaksakan 16 digit. Perlihatkan bahwa rekening tidak ada karena staff demo tidak mendapat permission keuangan. Perbarui alamat/kontak uji yang baru, reload dan lihat keberhasilan. Perubahan bisnis membuat `verify` terhadap sumber asli berbeda; gunakan database demo disposable jika ingin menulis tanpa mengubah lab verifikasi sumber.
4. Login admin: audit metadata terlihat, nilai lama/baru tidak dicatat. Admin bisa membuat user, memberikan permission+assignment eksplisit, dan menonaktifkan akun; admin sendiri tidak otomatis membaca profil pribadi.
5. Tunjukkan evidence PostgreSQL, backup restore dan benchmark. Bedakan local AES lab dari target OpenBao/TLS. Jelaskan metadata yang masih terlihat dan risiko aplikasi+kunci ikut dikuasai.

Untuk slot 15 menit, tambah penjelasan model ancaman, AAD tamper/wrong-key tests, kontrak DTO, grant `app_user`, benchmark 10.000 record dan batas metriknya, backup corruption rejection, serta rencana deployment bertahap. Ikuti ketentuan presentasi yang akhirnya dikonfirmasi panitia; dua PDF mempunyai durasi/submission berbeda.

Jalankan ulang bukti tanpa menampilkan data:

```powershell
.venv/Scripts/python -m pytest -q --junitxml=evidence/security-tests.xml
.venv/Scripts/python scripts/verify_security.py
cd apps/web
npm run test:e2e
```

Browser test memakai credential lokal, memeriksa empat role, XSS, CSRF, IDOR, pagination dan mobile. Tes alamat mengembalikan nilai awal dalam finally; jangan menjalankan benchmark/migrasi bersamaan dengan mutasi browser. Trace/screenshot otomatis dimatikan agar plaintext/token tidak masuk artifact. Credential/read source tidak disertakan pada evidence publik.
