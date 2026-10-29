# Catatan penyusunan paket konteks

- Seluruh bahan baru berada di docs/report/. Tidak membangun ZIP atau PDF,
  mengubah aplikasi/kripto/SQL, menjalankan benchmark, ataupun mengubah server/DB.
- Dua PDF panitia dibaca ulang; halaman daftar luaran dan pengumpulan juga
  diperiksa secara visual. Hasilnya diparafrase, bukan menyalin seluruh PDF.
- Basis kode 4877fc7 memuat main 96c9edb. Kode/evidence historis tetap memiliki
  commit dan waktu sendiri; basis dokumen bukan otomatis commit yang diukur.
- Sebanyak 89 sumber kode/metadata dipilih dan diikat hash. Builder tidak membaca
  dataset panitia, known-values privat, kredensial, token, unseal share atau kunci.
- Tabel hasil dihasilkan dari JSON/CSV yang ada, termasuk kegagalan target.
  Resource menggunakan median dari median per-run dan maksimum peak per-run.
- SBOM di appendix/sbom/ dibentuk dari deklarasi saat snapshot, terpisah dari
  SBOM root yang masih membutuhkan penyesuaian. Ketiganya valid schema CycloneDX;
  validasi itu bukan scan CVE atau kelengkapan environment deployment.
- Draf lama yang hanya mengakui baseline telah diganti. Hasil DB/leakage/1M kini
  dibahas; rencana API, ketidaksesuaian format masking runtime, hasil gagal dan
  kekurangan operasional tidak ditutup-tutupi.
- Validator memeriksa hash sumber, konsolidasi bab, tautan yang tetap di folder,
  kesamaan CSV/JSON, aritmetika/target dan keterkinian bukti schema SBOM. Test
  negatif mengubah angka, label target, denominator, link, hash dan SBOM pada
  salinan sementara untuk membuktikan kesalahan ditolak.
- Buku lengkap tidak dibaca ulang pada sesi ini. Nomor halaman buku dan sign-off
  reviewer manusia tetap perlu verifikasi sebelum PDF final.
- Audit luaran menambahkan inventory-report.csv, risk-matrix.csv dengan enam
  faktor awal,18 salinan evidence JSON dan indeks2.016 raw gzip. Sampel anggota
  pada inventory tidak disalin; pola menjadi deskripsi skematis berlabel.
  Inventory v1.2 dan assessment before_v1 pada provenance profile dibedakan.
  Raw tetap di repo; calon PDF eksternal belum dinyatakan final.

Perintah reproduksi dan cara memakai paket berada di [README.md](README.md).
Ringkasan pemeriksaan: [context_validation.json](context_validation.json) dan
[qa_summary.json](qa_summary.json). Keduanya bukan audit seluruh Git history/log/PII
atau pengesahan persyaratan lomba secara menyeluruh.
