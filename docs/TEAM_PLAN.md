# Rencana Tim Final (26-29 Oktober)

Acuan: PDF "Rancangan Hardening Final: Policy-Driven Leak-Resilient Data Protection" + penyesuaian
di `docs/contracts/CONTRACT.md` (kode_bank masuk domain FIN, 3 orang bukan 4, kontrak format bersama).
Submit target internal: Kamis 29 Okt sebelum 18.00 WIB (batas resmi 23.59 WIB).

## Pembagian
| Orang | Modul | Prompt |
|---|---|---|
| Alby | A: infra, OpenBao, crypto toolkit, protection profile, migrasi, role DB, backup/restore | `PROMPT_A_CRYPTO_MIGRATION_BACKUP.md` |
| Teman CRUD | B: Service App (mode plain + protected), access control, test API | `PROMPT_B_SERVICE_APP.md` |
| Delf | C: datagen + benchmark, leak simulation, leakage budget, evidence, targets, SBOM, koordinasi laporan | `PROMPT_CODEX_DATAGEN_BENCHMARK.md` lalu `PROMPT_C_VERIFY_EVIDENCE.md` |

## Langkah pertama (Senin malam, 30 menit, bersama)
1. Commit `AGENTS.md`, `docs/contracts/CONTRACT.md`, semua prompt ke `main`. Semua orang pull.
2. Teman CRUD konfirmasi bahasa backend. Jika bukan Python, dia wajib memakai test vector kontrak.
3. Sepakati keputusan nama (dienkripsi, sesuai kontrak) dan matriks peran di Prompt B.
4. Pastikan izin Write GitHub semua anggota beres.
5. Masing-masing buat branch: `feat/crypto-migration`, `feat/service-app`, `feat/verify-bench`.

## Jadwal
| Waktu | A (Alby) | B (CRUD) | C (Delf) |
|---|---|---|---|
| Sen malam | Tahap 1 infra OpenBao + TLS | MODE=plain jalan di baseline | datagen 100k + `targets.md` + baseline benchmark DB 3x |
| Sel pagi | Tahap 2 toolkit + test vector | Endpoint + matriks peran (plain) | Baseline benchmark API (MODE=plain) 3x |
| **Sel 12.00** | **Sinkron: baseline before terekam semua -> migrasi boleh jalan** | | |
| Sel siang | Tahap 3 profile + skema + role | Integrasi crypto (test vector) | leak_sim + leakage_budget di baseline |
| Sel malam | Tahap 4 migrasi `protected_734` + `protected_100k` | MODE=protected | Runner security tests |
| Rab pagi | Tahap 5 backup/restore/tamper/retention | Test akses lengkap + header/cookie/XSS | Leak sim + leakage budget pada protected |
| Rab siang | Tahap 6 rotasi (opsional) + perbaikan bug | Perbaikan bug | Benchmark after (urutan B-P-P-B) |
| **Rab 20.00** | **CODE FREEZE. Merge semua ke main. Jalankan seluruh evidence sekali lagi dari main.** | | |
| Rab malam | Tulis bab laporan modul A | Tulis bab laporan modul B | Gabung laporan + evidence_index |
| Kam pagi | Uji dari clone bersih (README) | Rekam video demo cadangan | SBOM + scan rahasia final |
| Kam siang | Slide final (bersama) | | |
| **Kam <18.00** | **Submit Drive + Form, cek akses incognito** | | |

## Aturan kerja dengan Codex
- Satu sesi Codex per modul, di branch masing-masing, dengan prompt modul. Jangan satu sesi untuk semua.
- Setiap Codex selesai satu tahap: jalankan test, review diff (cari: kunci/password di kode, fallback
  plaintext, query string concat, log berisi data), commit, push.
- Merge ke main lewat PR, direview satu anggota lain (bukti verifikasi hasil AI).
- Jangan menjalankan migrasi pada `baseline_100k` sebelum sinkron Selasa 12.00.

## Struktur laporan (bab = tantangan soal)
1. Pendahuluan, ruang lingkup, adaptasi dump (MySQL -> PostgreSQL)
2. Arsitektur, trust boundary, threat model
3. T1 Penemuan dan inventarisasi (scanner, ground truth, evaluasi, k-anonymity)
4. T2 Pengurangan nilai data (protection profile, AEAD+AAD, domain kunci, bidx, leakage budget)
5. T3 At rest / in transit / in use (+ batas setiap kontrol)
6. T4 Backend dan frontend
7. T5 Bukti keamanan dan kinerja
8. T6 Panduan penerapan bertahap (Roadmap Level 1-5 buku, biaya, rollback, risiko sisa)
9. Keterbatasan dan risiko residual
10. Referensi, SBOM, indeks evidence

## Tiga sorotan presentasi
1. Assessment-to-Protection: scanner -> profile -> migrasi.
2. Leak it on purpose: ESCE/DIE/ELS/DBR + k-anonymity sebelum vs sesudah (termasuk temuan kode_bank).
3. Blast radius: finance key bocor -> hanya domain FIN terbuka.
