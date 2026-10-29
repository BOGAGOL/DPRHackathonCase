# Handoff Modul C untuk Alby, Zhafif, dan agen mereka

29 Oktober 2026 WIB · Delf · branch `perf/keyservice-latency`.
`origin/main` **a746c6c** sudah masuk melalui merge **f370e13**, tanpa konflik.
**PR ini menunggu review/approval Alby; jangan merge otomatis.**

## Yang sudah dikerjakan sejak 27 Oktober

- Datagen utama `baseline_1m`: 734 sumber + 999.266 sintetis, seed 42;
  validasi memisahkan sumber/sintetis. `baseline_100k` dan sumber `postgres` dipertahankan.
  Snapshot dan known-values berada di luar repo. Sebagian pekerjaan C sudah ada di main;
  dokumen ini merangkum keseluruhan, bukan hanya diff PR.
- Baseline awal DB 100k/1M, masing-masing 7 skenario × 3 run, serta backup/restore
  ke DB sementara. Investigasi Python versus pgbench memisahkan biaya server/driver.
  Backup/restore 1M dan pgbench yang terdampak baterai mendapat pengukuran pengganti;
  data lama tetap berlabel. Workload awal 21 run tidak terdampak dan tidak diulang.
- Scanner v1.1 lalu **v1.2.0**: NIK nonstandar, kategori, impact per tipe, functional
  hanya konsisten 1,0 dengan rasio unik sumber <=0,8, label map evaluator dan HTML cetak.
  Ground truth `scanner/ground_truth_eval.csv`/metodologi Alby tidak diubah.
  Evaluasi v1.2: precision **96,30%**, recall **100%**, F1 **98,11%**, in-sample;
  satu false positive `kode_bank`. Scan after DB + dump 100k tersedia.
- Mengoperasikan migrator A pada laptop untuk protected 100k/1M; validasi seluruh
  field lulus 100.000/1.000.000 baris. TLS baseline bench/scanner tetap opsional,
  protected verify-full. pg_stat_statements dipakai melalui admin terpisah.
- Leak simulation, leakage budget dan residual before/after penuh; adapter protected
  memakai toolkit asli, mapping `legacy_row_id` ke UUID `anggota_id`, dekripsi selektif,
  dan parity nyata 1.000 kunci per skenario baca per skala tanpa mismatch.
- Dua sesi resmi DB **naive_v1** dan **v2**, diagnosis/optimasi transport, power guard,
  worker detached dan publikasi evidence. Token benchmark kini hanya lookup-self:
  tidak membaca root/auto-issue/renew; gate awal TTL >=3 jam, antarblok >=90 menit.

## Perubahan toolkit dan dampak ke app — review Alby

Panduan desain: [REVIEW_KEY_SERVICE_LATENCY.md](../../toolkit/REVIEW_KEY_SERVICE_LATENCY.md).
Kalimat “benchmark ulang belum dimulai” di panduan tersebut adalah catatan sebelum
pengukuran; hasil resmi terkini ada di bagian berikut.

| File relatif terhadap `toolkit/` | Perubahan/dampak |
|---|---|
| `dprcrypto/https_pool.py` (baru) | Session `http.client.HTTPSConnection` persisten, pool maksimum 8/idle 60s, CA + hostname + TLS >=1.2, respons maksimum 4 MiB, tanpa retry/redirect. |
| `dprcrypto/openbao.py` | Default transport `https_pool`; `DPR_OPENBAO_HTTP_TRANSPORT=httpx` memilih transport lama secara eksplisit. Error tetap fail closed. |
| `dprcrypto/bidx.py` | API tambahan `BlindIndexer.digests`, maksimal 100 pasangan, NULL/urutan/domain v1 tetap. Insert benchmark menggabungkan tiga HMAC menjadi satu RPC. |
| `dprcrypto/keys.py` | Statistik agregat cache hit/miss/batch saja; tidak menyimpan plaintext, KEK atau search key. |
| `tests/test_https_pool.py`, `tests/test_latency_features.py` | Test TLS/pool/error/batch/statistik. |
| `NOTES.md`, `REVIEW_KEY_SERVICE_LATENCY.md` | Keputusan, hasil diagnosis dan batas keamanan. |

Format blob v1, AAD, normalisasi, bidx dan wrapped DEK tidak berubah. HTTPX lama
sudah keep-alive: perbaikan mengurangi overhead dispatch/session, bukan memperbaiki
handshake baru per request. NIK full lookup masih tiga RPC: HMAC + unwrap PII + FIN.

**Default cache OFF berlaku pada benchmark**, bukan perubahan default umum toolkit:
`KeyManager` tetap default 15 detik/256 entri. App terbaru
`app/backend/service_app/crypto.py` sudah memakai `cache_ttl=0, max_entries=0`.
App akan memakai transport baru saat toolkit diperbarui dan proses dimulai ulang;
API `digest` lama tetap tersedia. Batch insert app perlu adopsi tersendiri bila diinginkan.
Kompatibilitas live app dengan transport baru belum diuji pada sesi handoff ini.
Cache 60s hanya eksperimen smoke; p95 memburuk, sehingga resmi v2 **cache OFF**.
Jika diaktifkan, revokasi dapat terlambat sampai sisa TTL; penghapusan RAM best effort/lazy.

## Hasil keamanan dan batas klaim

ESCE diukur pada **25 kolom AEAD kontrak**, bukan seluruh taksonomi data pribadi.

| Skenario, kedua skala | ESCE 100k / 1M | DIE | Kemampuan yang terbuka |
|---|---:|---:|---|
| Baseline dump | 100% / 100% | 100% | Plaintext |
| Protected tanpa kunci | 0% / 0% | 0% | Tidak meminta decrypt |
| Dengan kemampuan PII | 83,6734% / 83,6735% | 100% | PII saja |
| Dengan kemampuan FIN | 16,3266% / 16,3265% | 100% | FIN saja |
| Dengan kemampuan search | 12,2449% / 12,2449% | 100% | Kamus HMAC lengkap NIK/email/pengguna; bukan dekripsi AES |

DBR/probe ACL membuktikan domain lain ditolak. FIN membuka identifier seperti
rekening/NPWP: **jangan mengklaim semua identitas tetap tersembunyi saat FIN bocor**.
Token simulasi dicabut. Kamus lengkap sintetis adalah kondisi batas atas, bukan
asumsi penyerang nyata sudah memiliki baseline. ELS mencatat equality/frekuensi;
NULL, panjang ciphertext, REF dan legacy mapping tetap tampak.

Residual REF4 + age_band + pola NULL, kombinasi 1–3 atribut: min k **136 (100k)**,
**1362 (1M)**; subset sumber 734 tetap **k=1**, sintetis 135/1361. Repetisi sintetis
membesarkan k populasi penuh. Ini bukan jaminan anonimitas sumber 734. Scanner after
kadang menganggap nama kolom ciphertext sebagai quasi; gunakan residual terpisah,
bukan k=1 ciphertext sebagai bukti identitas terbuka. A5 aggregate-only di main
mengatur interface analis, tidak menghilangkan REF pada dump/tabel dasar.

## Benchmark resmi dan status target

Per sesi: **112 run**, 100k lalu 1M; 2 blok B-P-P-B per skala, empat run per
mode/skenario, concurrency 8, ukur 60s/warmup 10s, korpus sama/seed 42, tulis rollback.
Kedua sesi nol error, integritas akhir cocok. V2 seluruh blok AC valid; 1.585 sampel
resource tanpa kegagalan koleksi. Baseline awal tanpa pg_stat_statements adalah sesi
historis berbeda; bandingkan B/P dalam sesi resmi yang sama.

Contoh `read_by_nik`, median p95 ms dan throughput req/s:

| Skala | Naive B p95 / req/s | Naive P p95 / req/s | V2 B p95 / req/s | V2 P p95 / req/s |
|---|---:|---:|---:|---:|
| 100k | 6,604 / 2086 | 78,181 / 153 | 5,494 / 2492 | 37,734 / 300 |
| 1M | 5,747 / 2392 | 78,967 / 155 | 6,064 / 2260 | 38,624 / 294 |

P95 protected NIK turun sekitar 51% antarsesi. **Naive maupun v2 gagal P01 rasio,
P01A absolut, P02 throughput pada semua skenario; P03 error lulus.** API **BELUM DIUJI**.
Target `8c09a25` (28 Okt 13:37 WIB) mendahului run; tidak dilonggarkan setelah hasil.
db_time adalah mean SQL execution/request, bukan p95 server. Waktu non-DB tersedia
berdampingan; misalnya NIK v2 SQL protected 0,142/0,180 ms per request untuk 100k/1M.

V2 selesai 29 Okt **01:08:48 WIB**, evidence commit **6077b10**. Produksi dipin
**8a11ff7**, orchestration **bd5721e**. Merge main berikutnya membawa profil A5;
`production_manifest` sengaja menolak HEAD baru untuk replay sesi lama. Reproduksi
snapshot historis memakai checkout terisolasi `6077b10`, bukan melemahkan gate atau
menamai kode pascamerge sebagai kode yang diukur. Benchmark baru tetap perlu instruksi.

## Peta evidence utama

Semua path berikut relatif terhadap root repo; mulai dari ringkasan, bukan raw.

| Kebutuhan | Path |
|---|---|
| Dataset/validasi | `evidence/datasets/baseline_100k.json`, `baseline_1m.json` |
| Baseline awal + backup/restore | `evidence/benchmark/baseline/`, `baseline_1m/`; gangguan/pengganti di `benchmark/NOTES.md` |
| Runner/pgbench | `evidence/benchmark/runner_overhead.json`, `crosscheck_pgbench.json` |
| Migrasi nyata | `evidence/migration/validation-protected_100k.json`, `validation-protected_1m.json`; `evidence/overnight/resume_completion_20261028.json` |
| Scanner | `evidence/scanner/evaluation_v1_2.json`, `evaluation_regex_only.json`, `before_v1_2/`, `after_v1_2/` |
| Leakage/DBR/ELS | `evidence/leakage/after_summary.json`, `protected_100k/`, `protected_1m/`; hasil leak di `evidence/leak/` |
| Residual/comparison | `evidence/leakage/protected_{100k,1m}/residual_after.json`, `before_after.csv` |
| Parity/vector/no-key | `evidence/benchmark/keyservice_latency/verification.json`, `https_pool_v2/parity_cache_0.json` |
| Diagnosis transport | `evidence/benchmark/keyservice_diagnosis.json`, `keyservice_latency/` |
| Resmi lengkap | `evidence/benchmark/bppb_compare.json`, `bppb_v2_compare.json`, `bppb_versions_summary.md`, kedua `*_session.json`; raw gzip di `bppb_{100k,1m}/` dan `bppb_v2_{100k,1m}/` |
| Target sebelum run | `docs/targets.md`, `evidence/targets_commit.json` |
| Regresi pascamerge | `evidence/integration/modC_handoff_20261029.json` dan dua JUnit `modC_pr_{core,scanner}_20261029.xml` |

Audit `docs/team_status_20261028.md` adalah snapshot main **ed88ecd** sebelum A5/B4;
jangan gunakan blocker lamanya sebagai status terkini. Main kini memuat bukti A5 dan
acceptance A/B di `evidence/access-control/analyst_suppression.json` serta
`evidence/acceptance/post-a5-summary.json` (scope lab/VM berbeda dari pg-dpr).

## Yang masih terbuka dan cara melanjutkan

- **A / Alby:** review delapan file toolkit di atas, terutama pool TLS/error/close,
  batch HMAC dan kompatibilitas konsumen. Setujui sebelum merge. Paket deploy/acceptance
  A5 terbaru sudah masuk dari main; penerapan/retest transport baru pada deployment
  tetap terpisah dari bukti lama. Tidak ada apply A5/restart/rotasi pada sesi handoff.
- **B / Zhafif:** validasi live app dengan toolkit baru, termasuk fail-closed dan
  lifecycle client; pertahankan cache OFF dan query A5 aggregate-only. A5/B4 sudah ada
  di main, bukan blocker implementasi lama. Benchmark API 7 skenario dan rollback
  workload tulis masih perlu persiapan/instruksi terpisah; hasil DB tidak mengesahkan API.
- **C / Delf:** lengkapi `docs/evidence_index.md`, `evidence/summary.json`, runner
  gabungan `evidence/access-control/db-roles.json`, scan final S05/S06
  `evidence/secrets-and-logs.json`, SBOM `docs/sbom/`, dan reproduksi clone bersih/paket
  laporan. Path tersebut belum tersedia; jangan menandai seluruh target keamanan lulus.
  Dump logis bukan bukti physical-file/WAL/log/temp. Klaim performa harus tetap memuat
  kegagalan target; laporan/PDF/slides/submission bukan selesai hanya karena PR ini ada.

Regresi setelah merge: toolkit **108 PASS/1 SKIP**, benchmark **96 PASS**, verify
**32 PASS**, scanner **193 PASS/1 SKIP**. Skip: integrasi OpenBao disposable dan
scanner DB opt-in. Satu kegagalan awal test snapshot pascaperubahan profil A5 disimpan
di JUnit `modC_pr_core_20261029_initial_failure.xml`; test kini memakai snapshot historis
dan membuktikan perubahan file ditolak. Gate runtime tidak diubah. Reproduksi unit:

```powershell
$env:DPR_CRYPTO_INTEGRATION = '0'
.\.venv\Scripts\python.exe -m pytest toolkit/tests benchmark/tests verify/tests -q
.\scanner\.venv\Scripts\python.exe -m pytest scanner/tests -q
```

Sesi handoff tidak menjalankan benchmark, migrasi, atau perubahan DB/OpenBao.
Rahasia/dump/known-values tetap `DPR_PRIVATE_DIR=C:\dev\dpr-private`;
`DPR_SECRETS_DIR=C:\dev\dpr-private\openbao`. Jangan mencetak isi atau menyalinnya ke repo.
