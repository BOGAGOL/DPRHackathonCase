# A5 — 28 Oktober 2026

Instruksi tim mengesahkan pengetatan ACL dan pembaruan CONTRACT bagian 10.1. View per
record tetap internal; analyst_summary merilis lima marginal independen dengan HAVING
count(*) >= 5. Nama/tipe kolom stabil: dimension text, value text nullable,
anggota_count bigint. Fungsi age lama diarahkan ke view tersupresi agar tidak menjadi bypass.

Tidak mengubah app/ sesuai batas tugas terbaru. analytics.py masih bergantung pada raw view;
deploy harus berkoordinasi dengan B. Marginal tidak mendukung cohort gabungan; total DTO null
dan filter cohort ditolak sampai B menyediakan interface terfilter yang disupresi di SQL.
Tidak mengklaim differential privacy/k-anonymity gabungan atau ketahanan dari inferensi temporal.

Upgrade terpisah menjaga password/LOGIN/grant B dan data. Restore archive lama juga diperketat
sebelum CONNECT. Profile hanya berubah hash provenance kontrak, bukan format enkripsi/kolom;
protection_version tetap 1. Checkpoint profil lama tidak boleh di-resume memakai hash baru.

Docker Desktop lokal merespons HTTP 500 saat mulai pengerjaan; alternatif lab native PG18
disiapkan di luar repo. Tidak mengakses atau menerapkan perubahan pada laptop benchmark Delf.
Hasil aktual dan versi/transport dicatat oleh test pada evidence/access-control/analyst_suppression.json.

Verifikasi akhir: suite Modul A 323 PASS, 8 SKIP (integrasi opt-in lainnya), termasuk
uji A5 nyata PostgreSQL 18.6 Windows pada cluster sementara. 31 check A5 PASS:
SQLSTATE 42501 untuk raw table/view/column, kelompok 1–4 dan NULL4 tidak tampil,
label/jumlah kelompok 5–6 benar, NULL5 tampil, legacy function ikut tersupresi,
upgrade idempoten menjaga row hash, LOGIN migrasi dan grant tabel aplikasi,
PUBLIC column bypass ditolak, serta custom pg_dump/pg_restore dengan ACL lama
berhasil diperketat dan diterima oleh validasi keamanan restore. Dump uji hanya
di memori; tidak ada temporary dump plaintext. Unit restore juga membuktikan
CONNECT tidak dipublikasikan jika upgrade ACL gagal. TLS tidak menjadi scope
lab native ini; CLI penerapan tetap memaksa verify-full dan memiliki unit test.
Semua proses cluster uji dihentikan setelah test. app/ tidak berubah. Evidence
memuat hash sumber LF dan ringkasan suite dari JUnit eksternal, tanpa nilai anggota.

HTTP analytics pada test integrasi B/Service App lama masih menunggu query B
diganti sesuai CONTRACT 10.1; 8 skip tidak boleh dibaca sebagai bukti end-to-end
analytics atau recovery HTTP telah lulus dengan interface baru. Tidak menerapkan
upgrade pada database development persisten maupun VM dari sesi ini.
