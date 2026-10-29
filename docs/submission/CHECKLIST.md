# Checklist pengumpulan

Ini checklist paket kerja, bukan pernyataan semua kewajiban lomba telah selesai.
Status mesin yang dipakai tool: [requirements.json](requirements.json).

| No | Luaran | Status snapshot | Tindak lanjut / pemilik |
|---|---|---|---|
| 1 | Repo kode/config | Siap direview | Branch cleanup belum merge; sumber aktif terpisah dari arsip |
| 2 | README instalasi | Siap | Launcher setup/demo/verify tersedia; hasil clone bersih di evidence/reproduction/ |
| 3 | Laporan PDF | Draf sumber | Semua: review [draf](../report/DRAFT.md), lengkapi hasil, ekspor PDF final |
| 4 | Inventaris/klasifikasi | Ada, perlu review manusia | C + tim: sahkan ground truth dan keputusan ambigu |
| 5 | Matriks risiko | Ada, perlu review manusia | A/C: tinjau [CSV 29 kolom](../security/risk-matrix.csv) dan asumsi skor |
| 6 | Diagram arsitektur | Siap direview | A/B: cocokkan dengan konfigurasi lingkungan demo |
| 7 | Threat model singkat | Siap direview | Semua: sahkan batas aset/penyerang dan risiko tersisa |
| 8 | Skrip migrasi | Ada dan diuji sesuai scope | A/C: pilih evidence dataset/laptop yang sesuai klaim |
| 9 | Backup/restore | Ada, integrasi nyata | A: bedakan lab 17 record, hasil 734/100k, dan DR VM/key-plane |
| 10 | Skrip benchmark repeatable | DB tersedia, API parsial | C: B-P-P-B naive/v2/raw tersedia; setup API bukan measurement |
| 11 | Hasil before/after | DB tersedia, API belum lengkap | C: raw/median/resource/target DB tersedia; target kinerja gagal |
| 12 | Bukti akses | Ada, scope jelas | A/B: 143 lab dan 100 web; bukan sertifikasi semua dataset/VM internal |
| 13 | Daftar keterbatasan | Siap direview | Semua: [keterbatasan](../security/LIMITATIONS.md) masuk laporan/slide |
| 14 | SBOM/daftar dependensi | Siap dengan batas cakupan | Tim: [SBOM](../sbom/README.md); bedakan BOM sumber/environment/audit; digest/OS image belum dicatat |
| 15 | Presentasi | Konteks/outline | Semua: buat slide PDF/Slides final dan latihan demo |

## Pekerjaan sebelum dibekukan

- Leakage dan protected benchmark DB sudah tergabung. Pertahankan raw dan hasil
  gagal target. API belum memiliki seri ukur lengkap. S02 historis gagal pada salinan
  API tidak diganti labelnya dengan acceptance baru. Benchmark perlu koordinasi pemilik laptop.
- Lengkapi scan rahasia repo+history dan data pribadi pada log/temp/history/ekspor;
  screen saat packaging bukan penggantinya.
- Reviewer manusia memeriksa inventory, label acuan, matriks risiko dan klaim AI.
- Cocokkan angka laporan/slide dengan [indeks evidence](../evidence_index.md).
  Hasil gagal dan BELUM DIUJI tetap ditampilkan.
- Lengkapi prosedur custody/pemulihan key-plane, retensi/penghapusan arsip dan
  kebutuhan resource; DR penuh belum dibuktikan oleh unseal volume existing.
- Buat PDF laporan, slide final, lampiran raw yang disanitasi, dan paket sumber.
  Catat commit/hash, cek akses Drive dengan akun juri/tautan yang sesuai.
- Berkas yang dikumpulkan menjadi berkas yang dipresentasikan; perubahan setelah
  pengumpulan mengikuti ketentuan panitia. Tidak ada upload/submit otomatis.

Komponen yang belum tersedia boleh dibahas sebagai rencana, sesuai soal final,
tetapi tidak boleh diklaim sebagai implementasi yang berhasil diuji. Siapnya
source ZIP dan dokumentasi tidak mengubah status luaran PDF/slide/benchmark.
