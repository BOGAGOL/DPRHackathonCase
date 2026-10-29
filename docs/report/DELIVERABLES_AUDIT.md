# Audit kesiapan 15 luaran untuk penulis laporan

Tanggal pemeriksaan: **29 Oktober 2026 WIB**. Mapping pada gambar pengguna masuk
akal, tetapi “ada konteks” berbeda dari “ada artefak final” dan “semua uji lulus”.
Audit ini membaca snapshot branch submission, bukan menarik hasil yang mungkin
masih berjalan di laptop anggota tim atau branch lain.

## Jawaban untuk AI penulis

**Bahan untuk menyusun bagian laporan sudah tersedia dengan batas yang dinyatakan.**
Sebelum audit ini, inventory dan risk matrix masih digabung pada column-matrix,
dan beberapa bukti hanya berupa ringkasan/path sumber. Sekarang dilengkapi dua
CSV khusus, 18 salinan evidence metadata, serta indeks raw benchmark.
PDF final, slide final, pengesahan manusia dan hasil API yang belum tersedia
tidak boleh dianggap sudah terpenuhi.

| No | Luaran | Bahan lokal di docs/report | Penilaian dan yang masih perlu dilakukan |
|---|---|---|---|
| 1 | Repo kode/config | Bab4/7, source_manifest.json dan petaB01–B26 | Kode ada di repo PRIVATE; bukan menyalin seluruh source ke folder laporan. URL: https://github.com/BOGAGOL/juara1onno. Tim menyiapkan akses juri/lampiran source yang direview tanpa dataset/rahasia/.git |
| 2 | README instalasi | [Panduan operasional](07_PANDUAN_OPERASIONAL.md) dan README folder ini | Cukup untuk narasi langkah/prasyarat. README/runbook di repo tetap lampiran; beberapa narasi historis perlu diselaraskan sebelum submission final |
| 3 | Laporan DOCX/PDF | [DRAFT.md](DRAFT.md), [CONTEXT.md](CONTEXT.md) | Bahan sumber ada; PDF final terverifikasi belum ada dalam folder ini. Ada calon PDF di Downloads, belum ditetapkan sebagai final atau divalidasi terhadap snapshot terbaru |
| 4 | Inventory/klasifikasi | [inventory-report.csv](tables/inventory-report.csv), [column-matrix.csv](tables/column-matrix.csv), bab2, [evaluasi](evidence/scanner/evaluation_v1_2.json) | 29 atribut sumber, tipe/lokasi/kelas/risiko/alasan/rekomendasi/akses/search tersedia. Pola adalah deskripsi skematis, bukan salinan nilai anggota. Label manusia belum disahkan |
| 5 | Matriks risiko | [risk-matrix.csv](tables/risk-matrix.csv), [prioritas](02_ANALISIS_DATA_DAN_PRIORITAS.md), [keterbatasan](08_KETERBATASAN_DAN_REVIEW.md) | 29 kolom + skor/prioritas dan enam faktor dari assessment profile. Bukan penilaian risiko residual produksi atau matriks yang sudah ditandatangani |
| 6 | Diagram arsitektur | [PNG](assets/architecture.png), [SVG](assets/architecture.svg), [Mermaid](assets/architecture.mmd), bab3 | Siap dipakai dengan caption scope. Cache pada gambar adalah kemampuan toolkit; app/v2 cache OFF |
| 7 | Threat model singkat | [Bab3](03_RANCANGAN_DAN_KRIPTO.md) | Aset, aktor, capability, batas kepercayaan dan skenario/kontrol/residual tersedia; bukan hasil pentest penuh |
| 8 | Skrip migrasi | Bab4/7 dan [migration.csv](tables/migration.csv) | Kode ada di migration/ pada repo, dengan validasi734/100k/1M. Tidak perlu menempel seluruh script ke PDF; jelaskan algoritme/perintah/provenance |
| 9 | Skrip backup/restore | Bab7, operasi pada evidence_snapshot.json | Source scripts/backup/ tetap repo. Narasi dua mode, integritas, retensi dan hasil tersedia; DR key-plane penuh belum terbukti |
| 10 | Benchmark repeatable | Bab6/7; [session v2](evidence/benchmark/bppb_v2_session.json) | Runner DB/API ada di repo. Replay historis membutuhkan snapshot/gate yang sesuai dan credential privat. Ini bukan izin menjalankan benchmark baru |
| 11 | Hasil before/after | [db-benchmark.csv](tables/db-benchmark.csv), [resource](tables/v2-resources.csv), [compare v2](evidence/benchmark/bppb_v2_compare.json), [raw index](tables/raw-benchmark-index.csv) | DB naive/v2 lengkap untuk scope run, tetapi gagal P01/P01A/P02, P03 lulus. API [masih PLANNED](evidence/benchmark/api_bppb_compare.json), bukan hasil ukur |
| 12 | Bukti kontrol akses | [SQL A5](evidence/access-control/analyst_suppression.json), [recovery nyata](evidence/backup/service-recovery-integration.json), [browser deployment](evidence/acceptance/deployed-browser.json), [VM operator](evidence/service-app/access-control/vm-pentest-summary.json) | Salinan laporan checks aktual tersedia; scope31/143/100/65 berbeda. Bukti itu tidak mengesahkan full pentest atau semua lingkungan |
| 13 | Keterbatasan | [Bab8](08_KETERBATASAN_DAN_REVIEW.md) | Siap masuk laporan; jangan menghilangkan target gagal, residual, API pending, masking runtime dan gap operasi |
| 14 | SBOM/dependensi | [Lampiran SBOM](appendix/sbom/README.md), [dependencies.csv](tables/dependencies.csv) | Tiga CycloneDX valid schema;24 deklarasiPython/114 entri npm/2image. Tidak lengkap untuk Python transitif/OS/deployment/CVE |
| 15 | Presentasi | Konteks masalah, hasil, arsitektur dan batas klaim ada pada bab1–11 | Slide final bukan artefak di docs/report; belum ditemukan slide final pada source repo yang diperiksa. Tidak mengganti luaran slide dengan teks laporan |

## Cara menulis lampiran inventory dan risiko

`inventory-report.csv` dibentuk dari scanner v1.2; surrogate id dikecualikan.
Kolom sample_masked sengaja diganti deskripsi bentuk yang aman dari column-matrix,
dengan pattern_origin yang menyatakan asalnya. Itu **bukan contoh nilai asli**
atau klaim scanner mengeluarkan string deskripsi yang sama. Detected type/kelas
scanner tetap dipisahkan dari truth_pdp_class. allowed_roles/search_need adalah
rekomendasi assessment, bukan pengganti hak runtime/A5 pada bab5.

`risk-matrix.csv` memakai keputusan profile dan skor dari inventory before_v1
yang benar-benar dirujuk provenance profile. Enam faktor: sensitivity, volume,
exposure, exploitability, impact dan recovery. Inventory v1.2 adalah evaluasi
yang lebih baru; **jangan menyamakan kedua versi atau menyebut profile otomatis
dibangun dari v1.2**. Risiko awal acuan, skor scanner dan residual produksi berbeda.
Tidak dibuat angka residual atau tanda tangan reviewer palsu.

## Evidence dan hasil mentah

18 JSON terpilih disalin dari repo ke evidence/ dalam folder ini. Isinya laporan
checks, summary dan metadata, bukan credential atau dump. File disalin apa adanya
saat dibuat; SHA256 dengan normalisasi LF dicatat pada
[appendix_manifest.json](appendix_manifest.json) agar portabel antar platform.
Path sumber asli tetap tercatat. Salinan ini tidak berarti tes dijalankan ulang.

Raw DB B-P-P-B naive/v2 **ditemukan**: 2.016 gzip, total 196.559.219 byte, pada
empat direktori evidence/benchmark/bppb* di repo. Folder report menyimpan
[indeks path/ukuran/hash](tables/raw-benchmark-index.csv), bukan menduplikasi
sekitar187,5MiB raw. Penulis dapat menyusun angka dari compare/summary dan CSV;
lampiran raw untuk juri tetap harus disiapkan tim dari source repo setelah review.
Indeks ini tidak mencakup semua raw baseline awal, crosscheck atau histori lain.

## Yang belum tersedia atau tidak boleh dibuat dari asumsi

1. **Hasil API before/after** belum ditemukan pada snapshot: comparison PLANNED,
   scenarios kosong. Harus diukur oleh pemilik eksperimen dan disimpan; tidak bisa
   dibuat dari hasil DB. Rencana dua ulangan juga kurang dari minimum tiga.
2. **PDF laporan final terverifikasi** belum ada di docs/report. Calon
   `Laporan_Hackathon_DPR_RI_2026 (1).pdf` ada di Downloads (258.952 byte), tetapi
   belum diaudit/dinyatakan final. Bisa dibuat dari draf setelah review, bukan
   diakui final hanya karena file PDF tersebut ada.
3. **Slide final** belum ditemukan pada source repo yang diperiksa; bisa dibuat
   terpisah setelah angka dan klaim disepakati. Tidak menyimpulkan tidak ada slide
   di komputer/Drive anggota lain yang belum diberi akses.
4. **Review manusia** atas label/risiko/approval tidak boleh dibuat oleh AI.
5. **Audit penuh secret/history/log/temp/screenshot, physical-file/WAL theft dan
   DR key-plane lintas mesin** belum memiliki bukti final menyeluruh pada paket ini.
   Butuh akses/eksperimen khusus; dokumentasi atau unit test tidak menggantikannya.
6. **Kelulusan performa** tidak tersedia: hasil yang ada justru gagal target
   latensi/throughput. Tidak bisa diperbaiki dengan menulis ulang narasi hasil.
7. **Kesamaan format masking runtime** dengan contoh toolkit/panitia belum benar.
   Gap sudah dijelaskan; butuh keputusan/perubahan aplikasi dan retest bila diselaraskan.

Isi PDF yang aman adalah yang menyebut implementasi, bukti dan keterbatasannya
secara bersamaan. Folder ini cukup sebagai bahan penulisan, **bukan pernyataan
bahwa 15 luaran final telah selesai dan siap dikumpulkan semuanya**.
