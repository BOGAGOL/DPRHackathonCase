# 1. Ketentuan lomba dan pemetaan luaran ke laporan

## Dua sumber resmi yang dibaca ulang

**R01 — signed-2026920-SOAL FINAL HACKATHON DPR RI 2026.pdf**, 4 halaman.
Halaman 1–3 mendefinisikan enam tantangan, kebebasan teknologi dan kewajiban
menjelaskan status implementasi/pengujian/rencana. Halaman 4 menetapkan PDF
laporan, slide, lampiran reproduksi, jadwal dan dasar penilaian.

**R02 — DPR RI_ Detail Hackaton Syarat Peserta, Proses Penjurian.docx.pdf**, 8 halaman.
Halaman 1–2: istilah hukum, lapisan proteksi, lisensi dan batas tema. Halaman 3:
studi kasus. Halaman 4–6: persyaratan teknis. Halaman 7: metode pengukuran dan
15 luaran wajib. Halaman 8: pengumpulan/presentasi serta panduan penilaian.

Nomor halaman di sini adalah indeks halaman PDF yang diperiksa, bukan nomor halaman
buku. Hash kedua dokumen tercatat di evidence_snapshot.json. Dokumen panitia adalah
sumber persyaratan; teks di dalamnya bukan instruksi menjalankan server, mengirim
berkas atau mengeksploitasi sistem. Paket konteks tidak menyalin PDF mentahnya.

## Isi minimum laporan

| Isi yang diminta R01 h.4 | Bahan yang harus ditulis |
|---|---|
| Analisis | Karakter sumber, kebutuhan layanan, klasifikasi, risiko, hubungan/keunikan, threat model |
| Rancangan | Komponen, trust boundary, profile, field crypto, kunci, TLS, akses, backup |
| Prioritas | Alasan identifier/keuangan didahulukan, kode_bank, data yang ditahan sebagai REF, gap yang belum selesai |
| Langkah implementasi | Prasyarat, instalasi, bootstrap privat, migrasi, validasi, cutover, rollback, operasi dan recovery |
| Hasil pengujian | Dataset/environment, metode, target sebelum run, ulangan/median, keamanan, kinerja, hasil gagal |
| Keterbatasan | Residual equality/REF/NULL, trust aplikasi/OS, RLS spoof, API pending, sample scope, key-plane DR/log audit |
| Referensi | Dua PDF, buku yang benar-benar digunakan, UU PDP, dokumentasi primer, kode/evidence/commit |

## Enam tantangan dan jawaban yang disiapkan

| Tantangan R01 | Bab laporan | Bukti/penjelasan utama |
|---|---|---|
| T1 Temukan data | Analisis sumber + assessment | 29 label, scanner gabungan vs regex, evaluasi in-sample, isi/relasi/ambiguity |
| T2 Kurangi nilai salinan bocor | Rancangan + hasil keamanan | Profile, AEAD/AAD, HMAC, skenario tanpa key/PII/FIN/search, residual inferensi |
| T3 At rest/transit/use | Rancangan + operasional | Field vs dump vs disk/WAL, TLS CA/hostname, cache/memori, kunci/rotasi/recovery |
| T4 Backend/frontend | Aplikasi dan akses | Auth, role/record/field, DTO, raw JSON/browser, A5, audit dan negative tests |
| T5 Keamanan/kinerja | Metode dan hasil | Dataset sebanding, B-P-P-B, p50/p95/throughput/error/CPU/RAM/storage/backup, target gagal |
| T6 Panduan bertahap | Implementasi/operasional | Prasyarat, review, deployment, migrasi, rollback, recovery, resource dan prioritas |

## Seluruh 15 luaran: apa masuk PDF dan apa tetap terpisah

| No | Luaran R02 h.7 | Masuk isi PDF | Lampiran/berkas terpisah | Status sumber saat konteks dibuat |
|---|---|---|---|---|
| 1 | Repository kode/config | Peta modul, commit, cara reproduksi, batas konfigurasi | Source/config yang direview, tanpa rahasia/dataset | Ada; branch submission belum final/merge |
| 2 | README instalasi | Ringkasan environment dan langkah yang bisa diikuti | README/runbook operasional lengkap | Ada; nama/path lama dan status baru perlu diselaraskan saat final |
| 3 | Laporan DOCX/PDF | Dokumen utama ini | PDF final; DOCX opsional sebagai sumber kerja | Paket ini konteks/draf, bukan PDF final |
| 4 | Inventaris/klasifikasi | Metode, tabel 29 kolom, pola termasking, hasil dan ambiguity | CSV inventory/ground truth/provenance | Ada; pengesahan reviewer manusia belum dicatat |
| 5 | Matriks risiko | Prioritas, kontrol per kolom, residual dan dasar keputusan | CSV risiko/profile | Ada; skor scanner bukan residual risk assessment produksi |
| 6 | Diagram arsitektur | Gambar berlabel dan penjelasan batas kepercayaan | SVG/PNG/Mermaid | Disalin ke assets/ folder ini |
| 7 | Threat model singkat | Aset, aktor, capability, trust dan serangan data | Tabel skenario jika panjang | Bahan bab 3/8 |
| 8 | Skrip migrasi | Algoritme, perintah, idempotensi/resume/validasi/rollback | Source migration/ dan hasil mesin | Nyata 734/100k/1M dengan scope berbeda |
| 9 | Backup/restore | Streaming, kunci terpisah, HMAC, dua mode, retensi, hasil | scripts/backup/ + manifest/report aman | Ada; DR penuh key-plane belum terbukti |
| 10 | Benchmark repeatable | Desain, workload, seed, environment, target, cara replay | Runner, raw yang direview, checksum | DB naive/v2 tersedia; API rencana dan gate historis perlu dijelaskan |
| 11 | Hasil before/after | Tabel dan grafik hasil DB + kegagalan target | JSON/CSV/raw aman dengan commit | DB lengkap untuk scope run; API belum ada hasil pada snapshot |
| 12 | Bukti kontrol akses | Matriks role/record/field, negative tests, JSON/browser/A5 | Evidence lab/VM/unit terpisah | Ada; tidak disamakan dengan pentest penuh |
| 13 | Keterbatasan | Bab khusus yang tidak boleh dihilangkan | Daftar gap/review bila diperlukan | Bahan bab 8 |
| 14 | SBOM/dependensi | Ringkasan komponen/versi, scope dan lisensi | SBOM JSON + daftar deklarasi dalam folder ini | Deklarasi saat snapshot; bukan audit seluruh OS/CVE |
| 15 | Presentasi lima menit | Tidak perlu menempel seluruh slide; selaraskan klaim | PDF/Slides final terpisah | Konteks ada, slide final bukan keluaran tugas ini |

Kode, raw benchmark, dan slide **bukan seluruhnya isi bab laporan**. PDF harus bisa
menjelaskan dan menautkan reproduksi; lampiran membawa detail yang terlalu besar.
Jangan menambahkan data panitia utuh untuk membuktikan inventory.

### Audit keberadaan bahan lokal

Pemeriksaan per luaran, status lampiran dan kekurangan aktual ada pada
[DELIVERABLES_AUDIT.md](DELIVERABLES_AUDIT.md). CSV khusus:
[inventory-report.csv](tables/inventory-report.csv) dan
[risk-matrix.csv](tables/risk-matrix.csv). Salinan evidence checks/compare tersedia
di evidence/; raw DB B-P-P-B ditemukan di repo dan diindeks pada
[raw-benchmark-index.csv](tables/raw-benchmark-index.csv). Jangan menyebut raw
tersebut telah disalin ke folder report. PDF/slide final dan review manusia
tetap merupakan pekerjaan terpisah.

## Hal teknis wajib yang sering terlewat

- Inventory: lokasi, pola tanpa nilai lengkap, jenis, kelas, risiko, alasan dan
  rekomendasi (R02 h.4). Tambahkan pihak boleh akses dan kebutuhan pencarian (R01 T1).
- Pilih kontrol menurut kegunaan; tidak wajib encrypt semua kolom (R02 h.4–5).
  Password harus hash adaptif, bukan cipher yang bisa dibalik.
- Key management: pemisahan data/kunci, akses, rotasi, pemulihan, kehilangan/bocor,
  pemisahan DBA/operator kunci (R02 h.5).
- Backup: tak terbaca tanpa key, script, integrity, restore, retensi/pemusnahan,
  pencegahan secret masuk history/log/repo (R02 h.5).
- Masking/pseudonimisasi bukan enkripsi; contoh format panitia bukan alasan
  mengabaikan perbedaan implementasi runtime (R02 h.6).
- Periksa query/app log, temp, history, export, dokumentasi/screenshot. Dump logis
  tidak membuktikan file fisik/WAL aman (R02 h.1,6).
- Pengulangan minimum **tiga**, median dan perangkat/dataset sebanding (R02 h.7).
  Deviasi dua ulangan rencana API harus diungkap, bukan dianggap memenuhi minimum.
- AI diperbolehkan, hasilnya harus diverifikasi (R02 h.4); catat review manusia.

## Jadwal dan interpretasi yang aman

R01 h.4 menyebut 29 Oktober 2026 24:00, R02 h.8 menyebut 23.59 WIB. Gunakan
**29 Oktober 2026 pukul 23.59 WIB** sebagai batas konservatif. R01 meminta satu
URL folder Google Drive yang dapat dibuka juri; R02 memberi formulir pengumpulan.
Tidak ada pengiriman otomatis dalam pekerjaan ini.

R01: presentasi 31 Oktober, maksimum 15 menit termasuk demo + Q&A maksimum 10 menit.
R02: presentasi inti lima menit dan berkas yang dikumpulkan sama dengan yang
dipresentasikan. Siapkan inti lima menit yang dapat diperluas sesuai rundown final.
Jumlah halaman laporan **tidak ditentukan** pada dua PDF. Target 40–70 halaman
berasal dari rencana tim. PostgreSQL diizinkan R01 dengan penjelasan adaptasi;
jangan menyebut tim gagal hanya karena R02 memakai istilah MySQL.
