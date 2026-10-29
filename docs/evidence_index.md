# Indeks klaim dan evidence

Gunakan tabel ini untuk menulis laporan/slide. File JSON sendiri memuat tanggal,
scope dan pemeriksaan; baca isinya sebelum mengambil angka. Hasil environment
berbeda tidak boleh dijumlahkan menjadi sertifikasi dataset/VM yang sama.

| ID | Klaim yang boleh ditulis | Evidence | Scope / status |
|---|---|---|---|
| E01 | Scanner gabungan dievaluasi terhadap acuan 29 kolom | [evaluasi 1.2](../evidence/scanner/evaluation_v1_2.json), [nama disamarkan](../evidence/scanner/disguised_names.json) | In-sample; raw sebelum review manusia, bukan akurasi universal |
| E02 | Keputusan perlindungan diturunkan dari assessment + override | [profile](../policy/protection_profile.yaml), [build](../evidence/policy/build-profile.json) | 29 kolom, 25 AEAD, 3 bidx; tidak menghapus kolom |
| E03 | Format v1/AAD, tamper dan swap fail-closed | [vector bersama](contracts/test_vectors.json), [verifier](../evidence/crypto/vectors.json) | Fixture kripto sintetis; bukan hasil leakage seluruh artefak |
| E04 | Source demo 734 dipertahankan dalam migrasi | [validasi 734](../evidence/migration/validation-protected_734.json) | All rows/all fields pada lingkungan/tanggal laporan |
| E05 | Migrasi 100k tervalidasi | [validasi 100k](../evidence/migration/validation-protected_100k.json) | All rows/all fields; perhatikan laptop dan canonicalization source hash |
| E06 | Migrasi 1M nyata dan resume | [validasi 1M](../evidence/migration/validation-protected_1m.json), [targets](../infra/database-targets.json) | Semua baris/field sesuai scope laporan; jangan menyamakan laptop/lingkungan |
| E07 | Backup streaming + restore dua mode, integrity dan retensi | [backup](../evidence/backup/backup-report.json), [restore](../evidence/backup/restore-report.json), [tamper](../evidence/backup/tamper.json), [retensi](../evidence/backup/retention.json) | Data/dekripsi sesuai laporan; jangan sebut seluruh VM/key-plane pulih |
| E08 | PII KEK v1→v2, semua 100.734 wrapped DEK akhirnya versi baru | [rotasi](../evidence/keys/rotation.json), [percobaan awal](../evidence/keys/rotation-first-attempt.json) | Lab Alby; resumable, bukan versi wajib pada Bao baru/VM lain |
| E09 | SQL analyst aggregate-only, label kecil hilang | [A5 SQL](../evidence/access-control/analyst_suppression.json) | 31 pemeriksaan PG18.6 native, fixture 1–6/NULL, bukan endpoint VM langsung |
| E10 | Recovery gabungan A+B sesudah A5 | [summary](../evidence/acceptance/post-a5-summary.json), [recovery](../evidence/backup/service-recovery-integration.json) | 143 pemeriksaan; 17 record buatan sendiri, PG18/Bao TLS + Chrome nyata |
| E11 | Enam akun deployment memenuhi batas web yang diuji | [browser VM](../evidence/acceptance/deployed-browser.json) | 100 pemeriksaan, web read-only anggota; tanpa SSH/direct VM SQL/certifikasi commit |
| E12 | API/UI A5 mengikuti kontrak pada fixture | [analytics B](../app/evidence/access-control/analytics-a5.json), [backend B](../app/evidence/access-control/unit-tests.json), [browser B](../app/evidence/access-control/browser-tests.json) | SQLite/mocked UI sesuai scope; terpisah dari E10/E11 |
| E13 | Baseline awal 100k dan 1m diukur | [baseline100k](../evidence/benchmark/baseline/summary.json), [baseline1m](../evidence/benchmark/baseline_1m/summary.json) | DB/plain/before, bukan perbandingan protected/API |
| E14 | Vulnerability audit frontend pada waktu tertentu | [npm audit B](../app/evidence/access-control/npm-audit.json) | Snapshot lockfile pada tanggal laporan; bukan audit sistem/Python/container keseluruhan |
| E15 | Runtime lama dipisahkan dan jalur aktif lolos regresi | [cleanup](../evidence/submission/cleanup-stage1.json) | A325/10skip, B328/1skip; unit scope, tidak mengubah DB/server |
| E16 | Bahan pengumpulan dan source ZIP diperiksa | [verifikasi](../evidence/submission/verification.json) | Core369/10skip, ZIP tanpa Git/dataset lulus; 3 SBOM valid schema; luaran final tetap pending |

## Evidence gabungan terbaru

| ID | Klaim / status | Evidence | Batas |
|---|---|---|---|
| E17 | DB B-P-P-B naive/v2 100k/1M tersedia | [100k naive](../evidence/benchmark/bppb_100k/summary.json), [1M naive](../evidence/benchmark/bppb_1m/summary.json), [100k v2](../evidence/benchmark/bppb_v2_100k/summary.json), [1M v2](../evidence/benchmark/bppb_v2_1m/summary.json) | P01/P01A/P02 gagal, P03 lulus; raw per sesi dipertahankan |
| E18 | Leakage no-key/domain-key dan residual | [tabel before/after](../evidence/leakage/before_after.csv), [tabel laporan](report/tables/leakage.csv), [residual](report/tables/residual.csv) | Denominator field AEAD, metadata/equality tetap; lihat source path tiap tabel |
| E19 | Upgrade cryptography dan audit dependency | [review](security/CRYPTOGRAPHY_20261029.md), [upgrade](security/DEPENDENCY_UPGRADE_20261029.md), [SBOM](sbom/README.md) | Versi ≥50.0.2; direct API grep bukan bukti semua transitive aman; audit bertanggal |
| E20 | F-01 duplicate identity diperbaiki dan retest VM lulus | [F-01](../app/docs/F01_DUPLICATE_IDENTITY.md), [verification](../app/evidence/access-control/f01-deployment-verification.json) | Perbaikan terarah, bukan full pentest ulang |
| E21 | S02 historis INCOMPLETE_OR_FAILED | [DB roles](../evidence/access-control/db-roles.json) | Salinan API, dua kegagalan analis; bukan database resmi atau acceptance baru |
| E22 | S06 scan operasional terbatas | [plaintext scan](../evidence/secrets/plaintext-scan.json) | Public metadata matches reviewed; encoding/path/value exclusions eksplisit, bukan seluruh host/history |
| E23 | Nama/OID database benchmark resmi dipulihkan | [state](../evidence/benchmark/api_bppb_100k/db_swap_state.json) | Checksum/count/sequence cocok baseline sebelum swap; tidak menghapus kegagalan S02 historis |
| E24 | Reproduksi baru dari clone bersih | [indeks run](../evidence/reproduction/README.md) | Setup/import/assessment/hardening/enam akun/restore; status mengikuti run, bukan benchmark baru |

## Klaim yang belum dapat diberi PASS menyeluruh

- Bukti leakage dan DB before/after tersedia; keamanan universal dan kelulusan
  target kinerja tidak boleh disimpulkan. Benchmark API resmi belum lengkap.
- Scan seluruh repo+Git history, log/temp/history/ekspor/screenshot terhadap rahasia/PII.
- Pencurian file fisik/WAL, DR key-plane/VM lintas mesin dan secure erase semua salinan.
- Acceptance seluruh record pada setiap dataset tim dan identitas commit/internal VM.
- PDF laporan/slide final, review manusia dan akses folder pengumpulan.

Perubahan yang sudah digabung dibaca berdasarkan berkas dan commit. Jangan mengambil angka tanpa menyertakan
file, commit, dataset, lingkungan, scope dan batasnya. History kegagalan tetap disimpan.
