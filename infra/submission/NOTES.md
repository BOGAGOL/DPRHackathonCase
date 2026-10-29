# Keputusan alat pengumpulan

- Menggunakan root sumber aktif yang eksplisit, lalu menolak lokasi/file privat,
  dataset panitia, arsip historis dan environment lokal. `verify/` tetap disertakan
  walaupun implementasi verifikasi pada snapshot ini belum lengkap.
- ZIP dapat dibuat tanpa `.git`. Setiap file mendapat hash dan ukuran; isi ZIP
  dibaca ulang untuk memeriksa CRC/hash. Output lama tidak ditimpa.
- Status quality paket dipisahkan dari kelengkapan luaran. Dokumen draf dan
  benchmark yang belum lengkap tetap berstatus pending pada checklist.
- SBOM CycloneDX mencatat deklarasi Python, lockfile npm dan referensi image.
  Versi dari rentang Python, digest image, CVE dan dependency OS tidak ditebak.
- Screen credential hanya pemeriksaan pola terbatas. Pemeriksaan seluruh Git
  history, log, ekspor dan nilai pribadi tetap memerlukan pekerjaan terpisah.
- Tidak menyentuh database, material kunci, kontrak kripto atau konfigurasi VM.

Uji: `python -m pytest infra/submission/tests -q`. Panduan penggunaan dan cakupan:
[struktur paket](../../docs/submission/STRUCTURE.md).

Pembaruan final 29 Okt: denylist mencakup environment assessment/benchmark baru
dan accounts.md. Satu exception path persis evidence/secrets/plaintext-scan.json
mengikutsertakan receipt metadata S06 yang direview; sibling secrets lainnya tetap
ditolak. Content screen tetap berjalan. Composer reproduksi ikut freshness SBOM.
