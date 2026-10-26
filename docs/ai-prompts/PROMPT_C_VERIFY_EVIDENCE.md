# Prompt Modul C: Verifikasi, Leakage Budget, Benchmark, Evidence (pemilik: Delf)

Baca `AGENTS.md` dan `docs/contracts/CONTRACT.md` terlebih dahulu. Folder milikmu: `datagen/`,
`benchmark/`, `verify/`. Hasil mesin ke `evidence/`.

Bagian datagen + benchmark baseline sudah dirinci di
`docs/ai-prompts/PROMPT_CODEX_DATAGEN_BENCHMARK.md`. Kerjakan itu DULU (prioritas tertinggi, harus
selesai sebelum siapa pun menjalankan migrasi). Lalu lanjutkan bagian di bawah.

## 1. Simulasi kebocoran (`verify/leak_sim`)
`python -m verify.leak_sim --artifact <pg_dump file / db> --scenario <nama> --known-values <file>`
- `known-values`: daftar nilai asli yang dicari (diambil dari baseline oleh skrip, disimpan di luar
  repo, tidak dicetak). Pencarian pada artefak mentah (dump plaintext SQL, dump custom setelah
  `pg_restore -f -`, file data, backup terenkripsi).
- Skenario: `baseline_dump`, `protected_dump_no_key`, `protected_dump_with_pii_key`,
  `protected_dump_with_finance_key`, `protected_dump_with_search_key`, `backup_artifact_no_key`.
  Skenario "dengan kunci" mensimulasikan penyerang memegang kredensial OpenBao policy tertentu
  (gunakan token terbatas dari modul A).
- Juga jalankan scanner (`python -m scanner dump ...`) pada artefak yang sama, label `after`.

## 2. Leakage Survivability / Leakage Budget (`verify/leakage_budget`)
Hitung per skenario dan simpan di `evidence/leakage/<scenario>.json`:
- ESCE (Exact Sensitive Cell Exposure) = sel sensitif yang bisa dipulihkan persis / total sel sensitif non-null.
- DIE (Direct Identifier Exposure) = baris yang masih membuka minimal satu identifier langsung / total baris.
- ELS (Equality Leakage Surface) = kolom deterministik (bidx) + histogram frekuensi (jumlah kelas
  kesetaraan, ukuran kelas terbesar).
- DBR (Decryption Blast Radius) = domain/kolom yang terbuka bila satu kunci/policy bocor.
- Residual k-anonymity: kombinasi 1-3 kolom dari kolom yang MASIH plaintext di artefak (REF +
  age_band + pola NULL), jumlah baris unik dan k minimum. Bandingkan dengan baseline
  (sebelum: tempat_lahir + tanggal_lahir + jenis_kelamin unik 730/734).
Output tabel ringkas before vs after untuk laporan.

## 3. Uji integritas dan akses (runner)
`verify/run_security_tests`: menjalankan dan mengumpulkan hasil:
- Tamper ciphertext 1 bit, swap antar-record, swap antar-kolom -> decrypt gagal (pakai toolkit A).
- Uji role DB: analyst_user SELECT tabel dasar ditolak; backup_user tidak bisa UPDATE; auditor_user
  tidak bisa membaca anggota; app_user tidak bisa DDL. Hasil: `evidence/access-control/db-roles.json`.
- Kumpulkan hasil test API modul B dan backup modul A ke `evidence/summary.json` (lulus/gagal per uji,
  dibandingkan target di `docs/targets.md`).
- Scan rahasia: gitleaks (atau regex) pada repo + riwayat git; scan plaintext sintetis pada log
  aplikasi, log PostgreSQL (general/slow/error), folder temp, hasil ekspor. Hasil ke
  `evidence/secrets-and-logs.json`.

## 4. Benchmark after
Tambahkan adapter `benchmark/adapters/protected.py` (pakai toolkit A: bidx lookup + batch unwrap +
decrypt field yang dibutuhkan) dan adapter API (memanggil Service App MODE=plain vs MODE=protected).
Jalankan urutan baseline -> protected -> protected -> baseline, minimal 3 run masing-masing, laporan
median p50/p95, throughput, error, CPU, RAM, ukuran DB, waktu backup/restore. `compare` menandai
lulus/gagal terhadap `docs/targets.md`.

## 5. Evaluasi scanner
Jalankan `python -m scanner evaluate` dengan `scanner/ground_truth.csv` (label map), simpan ke
`evidence/scanner/evaluation.json`. Catat in-sample dan hasil test nama kolom disamarkan.

## 6. Dokumen
- `docs/targets.md` (DITULIS SEBELUM benchmark): fungsi 100% lulus, akses ilegal 100% ditolak,
  ESCE 0% untuk kolom AEAD pada dump tanpa kunci, tamper/swap 100% gagal, 0 secret aktif,
  restore 100% berhasil, p95 API umum <= 1.5x baseline, throughput >= 70% baseline, error tidak naik.
- `docs/evidence_index.md`: daftar setiap klaim laporan -> file evidence -> status
  (diimplementasikan+diuji / diimplementasikan / rencana).
- SBOM: `pip-audit`/`cyclonedx-py` untuk Python dan setara untuk app B, ke `docs/sbom/`.

## Definisi selesai
Senin malam: baseline benchmark 3 run + targets.md. Rabu malam: semua evidence terisi.
