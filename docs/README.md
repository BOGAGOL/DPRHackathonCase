# Dokumentasi dan bahan pengumpulan

Mulai dari [README proyek](../README.md). Dokumen ini memetakan implementasi aktif,
bukti yang tersedia, dan bahan yang masih perlu direview tim sebelum dikirim.
Quick-start tunggal: `python -m infra.reproduce setup`, lalu `verify`/`demo` dengan
input SQL privat. Hasil clone bersih ada di [indeks reproduksi](../evidence/reproduction/README.md).

| Bagian | Isi |
|---|---|
| [Kontrak](contracts/CONTRACT.md) | Format kripto v1, kolom, role, dan interface analis A5 |
| [Arsitektur](architecture/README.md) | Diagram, aliran data/kunci, batas kepercayaan |
| [Threat model](security/THREAT_MODEL.md) | Aset, pelaku, skenario kebocoran, kontrol dan sisa risiko |
| [Matriks risiko](security/RISK_MATRIX.md) | Keputusan 29 kolom, risiko scanner dan kebutuhan review |
| [Keterbatasan](security/LIMITATIONS.md) | Batas desain, pengujian, benchmark dan operasional |
| [Reproduksi](operations/REPRODUCTION.md) | Environment, test terpisah, migrasi, backup, release |
| [Operasional dan pemulihan](operations/OPERATIONS.md) | Prasyarat, custody, retensi, recovery dan resource |
| [Indeks evidence](evidence_index.md) | Klaim -> file -> scope -> status |
| [Konteks laporan](report/CONTEXT.md) | Fakta terkunci dan aturan penulisan berdasarkan bukti |
| [Draf laporan](report/DRAFT.md) | Narasi awal enam tantangan; bukan PDF final |
| [Konteks presentasi](presentation/CONTEXT.md) | Susunan slide, demo dan batas waktu |
| [SBOM](sbom/README.md) | Inventaris CycloneDX dan batas kelengkapannya |
| [Checklist](submission/CHECKLIST.md) | Lima belas luaran, pemilik dan pekerjaan tersisa |
| [Struktur/paket](submission/STRUCTURE.md) | File aktif, arsip dan aturan pembuatan ZIP |
| [Sumber dan asal-usul](submission/SOURCES.md) | Dua dokumen lomba, buku dan sumber teknis |

`PROJECT_CONTEXT.md`, `TEAM_PLAN.md` dan `ai-prompts/` menyimpan keputusan serta
sejarah koordinasi. Target kinerja ditetapkan di [targets.md](targets.md);
target bukan hasil. Jangan memperbarui ambang setelah melihat benchmark.

Status **TERUJI** selalu disertai lingkungan/dataset. **DRAF/PARSIAL/RENCANA**
tidak boleh disajikan sebagai keberhasilan implementasi. Belum ada verifikasi
terhadap folder Drive atau PDF/slide final di luar checkout ini.
