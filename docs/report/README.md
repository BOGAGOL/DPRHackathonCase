> **Snapshot konteks awal belum diselaraskan seluruhnya dengan HEAD.**
> Baca [pembaruan final 29 Oktober](UPDATES_20261029.md) terlebih dahulu.
> Manifest/tabel/evidence salinan lama dipertahankan sebagai snapshot bertanggal.

# Paket konteks laporan — Tim BOGAGOL

Paket ini disusun pada **29 Oktober 2026 WIB**, berdasarkan branch
`chore/submission-polish`, snapshot kode `4877fc7` yang sudah memuat `main` `96c9edb`.
Ini sumber penulisan, **bukan PDF final, pengesahan manusia, atau hasil benchmark baru**.
Seluruh materi baru untuk penulis dikumpulkan di folder ini. ZIP ditunda.

Untuk mengecek kesiapan setiap luaran, baca
**[DELIVERABLES_AUDIT.md](DELIVERABLES_AUDIT.md)**. Inventory dan risk matrix kini
punya CSV khusus;18 salinan evidence metadata ada di evidence/. Raw benchmark
tetap di repo dan mempunyai indeks path/ukuran/hash pada tables/.

## Cara memakai

1. Untuk AI yang menerima satu berkas: berikan **[CONTEXT.md](CONTEXT.md)** dan
   **[AI_PROMPT.md](AI_PROMPT.md)**. CONTEXT menggabungkan seluruh bab konteks dan tabel hasil.
2. Untuk penulisan bertahap, gunakan daftar bab di bawah. Angka penuh tersedia di
   [evidence_snapshot.json](evidence_snapshot.json) dan CSV pada `tables/`.
3. Diagram siap pakai ada di `assets/`; daftar dependensi/SBOM ada di `appendix/sbom/`.
4. [DRAFT.md](DRAFT.md) menyediakan kerangka narasi. Isi final harus mengikuti scope,
   hasil gagal, dan keterbatasan yang dicatat di paket ini.
5. Sebelum finalisasi, isi reviewer manusia, cocokkan hasil API terbaru bila memang
   sudah masuk repo, lalu lakukan review data pribadi dan ekspor PDF.

## Isi per bab

| Berkas | Tujuan penulisan |
|---|---|
| [01_KETENTUAN_DAN_LUARAN.md](01_KETENTUAN_DAN_LUARAN.md) | Dua PDF, enam tantangan, 15 luaran, isi laporan versus lampiran |
| [02_ANALISIS_DATA_DAN_PRIORITAS.md](02_ANALISIS_DATA_DAN_PRIORITAS.md) | Masalah, dataset, assessment, label, alasan prioritas |
| [03_RANCANGAN_DAN_KRIPTO.md](03_RANCANGAN_DAN_KRIPTO.md) | Arsitektur, trust boundary, threat model, format v1, domain, TLS |
| [04_IMPLEMENTASI_DAN_MIGRASI.md](04_IMPLEMENTASI_DAN_MIGRASI.md) | Tahap A1–A6, schema, ACL/RLS, migrasi/resume, rotasi |
| [05_APLIKASI_DAN_AKSES.md](05_APLIKASI_DAN_AKSES.md) | Endpoint, enam role, field/scope, A5, browser, masking, VM |
| [06_METODOLOGI_DAN_HASIL.md](06_METODOLOGI_DAN_HASIL.md) | Scanner, leakage, residual, DB before/after, API, resource dan backup |
| [07_PANDUAN_OPERASIONAL.md](07_PANDUAN_OPERASIONAL.md) | Instalasi bertahap, perintah, validasi, cutover, rollback, DR, biaya |
| [08_KETERBATASAN_DAN_REVIEW.md](08_KETERBATASAN_DAN_REVIEW.md) | Klaim yang dibolehkan/dilarang, gap, tindakan manusia |
| [09_REFERENSI_DAN_ATRIBUSI.md](09_REFERENSI_DAN_ATRIBUSI.md) | Daftar pustaka dan sumber primer yang bisa diperiksa |
| [10_PETA_BUKTI.md](10_PETA_BUKTI.md) | ID bukti, source path, cara membaca status/tanggal/commit |
| [11_TABEL_HASIL.md](11_TABEL_HASIL.md) | Tabel lengkap hasil terpilih yang diturunkan dari JSON/CSV |

## Koreksi terhadap konteks lama

- Migrasi **1M nyata**, leakage PII/FIN/search, serta DB B-P-P-B naive/v2 **sudah ada**.
  Pernyataan lama “baru baseline” tidak berlaku lagi pada snapshot ini.
- Kinerja DB **gagal P01/P01A/P02** dan **lulus P03**; optimasi bukan kelulusan target.
- API comparison masih `PLANNED`, `scenarios=[]`; dua ulangan rencana API berada di
  bawah minimum tiga kali. Tidak ada angka API after yang sah pada snapshot ini.
- Kompatibilitas format kripto tetap v1. Bukti aplikasi live sebelum transport baru
  tidak otomatis menjadi bukti semua komponen pascaperubahan.
- Ada evidence VM dari operator B yang lebih baru daripada pengujian web Alby;
  masing-masing dibahas terpisah, bukan dijumlahkan menjadi satu pengujian.

## Pemeriksaan paket konteks

```powershell
python docs/report/verify_context.py
python -m pytest docs/report/tests -q
```

Pemeriksaan hanya membaca sumber dan paket konteks; tidak memerlukan DB, token,
credential demo, benchmark, atau koneksi ke deployment. Hasil pemeriksaan berada
di [context_validation.json](context_validation.json). Manifest hash mengikat sumber
yang dibaca, bukan menjamin hasil historis telah dijalankan ulang pada commit baru.

Untuk regenerasi tabel setelah sumber berubah, gunakan environment dengan
`infra/submission/requirements.txt` dan jalankan
`python docs/report/build_context.py`, lalu `python docs/report/build_appendix.py`
dan ulangi pemeriksaan. Builder hanya
membaca kode/metadata terpilih dan menulis di folder report. Regenerasi tabel
tidak otomatis memperbarui interpretasi manusia atau validasi schema eksternal.
