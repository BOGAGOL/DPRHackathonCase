# Progres Modul B — 28 Oktober 2026

## Revisi A5/B4

Implementasi mengikuti CONTRACT 10.1/PR A #10, hanya perubahan source di app/.
Analytics membaca public.analyst_summary sebagai analyst_user. Kelompok 1–4 dan
labelnya dihilangkan; count integer >=5 dan total selalu null. Filter cohort lama
ditolak 422; UI hanya memilih dimension/value marginal yang sudah dirilis.
Tidak ada fallback per-record/role atau decrypt analytics. Fixture dua mode dan
skrip integrasi disesuaikan; setup lab existing tidak dijalankan.

Build Next.js dan 14 test browser lulus. Test khusus analytics 64 lulus. Regresi
backend final 328 lulus/1 skip, termasuk gate readiness A5. Hasil mesin dicatat di
app/evidence/access-control/unit-tests.json dan analytics-a5.json.
Fixture SQLite/mocked UI bukan validasi SQL A5 pada VM.

VM menurut log pengguna: PostgreSQL/OpenBao TLS, migrasi 734, verifier A, provisioning
enam akun, backend/web HTTPS dan login operator sudah berhasil. Angka 2 pada akun
staf berasal dari default assignment 1,2. Perintah perluasan ke 734 sudah diberikan;
hasil eksekusinya belum diterima. Jangan menandai scope 734 PASS tanpa hasil itu.

Berikutnya: rilis paket baru dan SQL A5 ke VM sesuai docs/DEPLOY_A5.md; terima evidence
apply/verify dan acceptance akun. Jangan mengubah pg-dpr/baseline/target benchmark
Delf. VM A5, benchmark resmi, dan systemd tetap belum selesai/NOT TESTED.
