# Aplikasi layanan DPR Secure

Baca `PROGRESS.md`, `DECISIONS.md`, `README.md`, `docs/SECURITY.md` sebelum mengubah kode. Scope checkout ini adalah aplikasi layanan dan toolkit lab; scanner Task 1 ada di direktori terpisah di luar checkout dan tidak boleh dimasukkan ke runtime web.

Jangan commit `.env`, `.local`, raw SQL/data/backup, credential atau key. Tidak mempublikasikan aplikasi/dataset dari task lokal ini. Output evidence harus disanitasi. Tes source SQL dapat skip pada clone yang tidak mendapat dataset panitia; dokumentasikan skip. Jangan mengeksekusi raw SQL dari input: parser whitelist dan parameterized inserts saja.

Jalankan tes yang sesuai perubahan, update status implementasi versus verifikasi secara terpisah. Docker/PostgreSQL/TLS/KMS adalah bukti berbeda. Jangan menandai NOT TESTED sebagai PASS atau mengklaim production-ready. Jangan menjalankan benchmark saat tes browser mengubah record; verifikasi source equality setelahnya. Credentials provisioning lokal acak, tidak dicetak/log. Proses lokal/DB baru hanya milik proyek; jangan menghentikan/menghapus instance lain.
