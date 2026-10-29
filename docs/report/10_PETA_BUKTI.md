# 10. Peta klaim–bukti dan cara sitasi

Path pada tabel ini relatif terhadap root repository, **bukan** file yang wajib
dibuka penulis hanya untuk memahami konteks. Nilai/interpretasi terpilih sudah
disalin ke evidence_snapshot.json dan tables/ di folder ini. Hash sumber ada pada
source_manifest.json. Kode dan JSON asli tetap acuan audit jika ada perbedaan.

| ID bukti | Klaim/bahan | Sumber utama root repo | Scope yang wajib ikut caption |
|---|---|---|---|
| B01 | Format/kolom/kewenangan v1 | docs/contracts/CONTRACT.md; policy/protection_profile.yaml | Keputusan normatif, bukan hasil pengujian |
| B02 | Ground truth 29 kolom | scanner/ground_truth_eval.csv; docs/ground_truth_methodology.md | Acuan review awal, id buatan tim dikecualikan |
| B03 | Scanner v1.2/regex | evidence/scanner/evaluation_v1_2.json; evaluation_regex_only.json; disguised_names.json | In-sample, raw_before_human_review; fixture nama tersamar terpisah |
| B04 | Dataset 100k/1M | evidence/datasets/baseline_100k.json; baseline_1m.json | Seed42, source/synthetic/all, source immutable |
| B05 | Profile dari assessment | evidence/policy/build-profile.json; policy/build_profile.py; overrides.yaml | Provenance inventory/override; bukan klasifikasi hukum otomatis |
| B06 | Crypto/vector/integrasi | evidence/crypto/vectors.json; integration.json; toolkit/tests/ | Public fixture sintetis; integration version/tanggal perlu disebut |
| B07 | Migrasi734/100k/1M | evidence/migration/validation-protected_734.json; validation-protected_100k.json; validation-protected_1m.json | All rows/all fields per lingkungan, bukan satu run gabungan |
| B08 | Operasi migrasi laptop | evidence/migration/laptop-timings.json; evidence/overnight/migration_1m/completion.json |100k timer dan 1M completion/storage berbeda operasi |
| B09 | Backup protected | evidence/backup/backup-report.json; restore-report.json; tamper.json; retention.json |100k single operational result,16 sample decrypt; bukan median 3 run |
| B10 | Rotasi | evidence/keys/rotation.json; rotation-first-attempt.json | Lab Alby,100.734 wrapper PII,v1→2,resume,all-field compare |
| B11 | SQL A5 | evidence/access-control/analyst_suppression.json; sql/protected/03_analyst_suppression.sql |31 checks,fixture kelompok 1–6/NULL,aggregate-only |
| B12 | Recovery layanan nyata | evidence/backup/service-recovery-integration.json; evidence/acceptance/post-a5-summary.json |17 record buatan,143 checks,PG 18/BaoTLS/API/Next/Chrome |
| B13 | Web deployment | evidence/acceptance/deployed-browser.json |100 checks/enam akun existing,web read-only anggota,tanpa SSH Alby |
| B14 | Operator VM/pentest preparation | app/evidence/access-control/vm-pentest-summary.json; vm-a5-verify.json; vm-golden-reset.json |734 record,8 akun pentest,1 guarded reset,65 smoke; bukan pentest penuh |
| B15 | Policy/DTO/aplikasi | app/backend/service_app/policy.py; schemas.py; repository.py; main.py; analytics.py; crypto.py | Implementasi aktual, termasuk format masking berbeda dan cache OFF |
| B16 | Baseline awal aktif | evidence/benchmark/baseline/summary.json; baseline_1m/summary.json; active_measurements.json | Sesi awal berbeda dari B/P resmi; pengganti AC untuk timing tertentu |
| B17 | DB naive_v1 | evidence/benchmark/bppb_compare.json; bppb_session.json |112 run,100k + 1M,4 ulangan/mode/skenario,target gagal |
| B18 | DB v2 | evidence/benchmark/bppb_v2_compare.json; bppb_v2_session.json; bppb_v2_{100k,1m}/summary.json |112 run,https_pool/cache OFF,1.585 samples,DB bukan API |
| B19 | Diagnosis transport | evidence/benchmark/keyservice_diagnosis.json; toolkit/REVIEW_KEY_SERVICE_LATENCY.md | Client lama already keep-alive,diagnosis bukan hasil kinerja akhir |
| B20 | Rencana API | evidence/benchmark/api_bppb_compare.json; benchmark/api/README.md |PLANNED,scenarios kosong,2 ulangan di bawah minimum 3,GET only |
| B21 | Target sebelum run | docs/targets.md; evidence/targets_commit.json |8c09a25 mendahului B/P; jangan longgarkan ambang |
| B22 | Leakage/DBR | evidence/leakage/after_summary.json; protected_100k/; protected_1m/; evidence/leak/ |25 kolom AEAD,artefak nyata,PII/FIN/search capability terpisah |
| B23 | Baseline/residual | evidence/leakage/baseline_100k/baseline_dump.json; baseline_dump.json; protected_{100k,1m}/residual_after.json |1–3atribut,source 734 masih k = 1,bukan DP |
| B24 | TLS/bootstrap | infra/NOTES.md; infra/openbao/init.py; infra/postgres/enable_tls.py; infra/vm/README.md |TLS aktual/probe versi; satu node/file backend,operator manual |
| B25 | Regresi setelah sync | evidence/submission/main-sync-20261029.json |377 core/10 skip,155 benchmark/verify/1 skip; tidak ada live benchmark baru |
| B26 | Launcher dan unit aplikasi VM | app/scripts/run_runtime.sh; app/deploy/dpr-api.service; app/deploy/dpr-web.service; scripts/deploy/install_app_services.sh | Hardening dan guard yang tersedia pada kode; bukan verifikasi semua opsi di setiap VM |

## Format sitasi/caption yang dianjurkan

“B18, evidence/benchmark/bppb_v2_compare.json, DB 100k, median 4 run/mode/skenario,
selesai 29 Okt 2026 01:08:48 WIB; kode produksi 8a11ff7/orchestration bd5721e.”
Untuk R01/R02 tambahkan halaman PDF yang benar. Untuk referensi web gunakan judul,
URL versi, tanggal akses dan mekanisme yang didukung. Untuk screenshot yang tidak
ada, jangan menulis “lihat gambar hasil” seolah sudah direkam; diagram pada assets adalah
rancangan, bukan screenshot deployment.

## Berkas status lama dan precedence

docs/team_status_20261028.md adalah audit main ed88ecd sebelum A5/B4. Handoff C
memuat catatan sebelum merge dan sebelum API setup terakhir. protected_pending.json
adalah status historis sebelum hasil after. README lama di luar folder ini masih
memuat teks “hanya baseline”. Pakai file hasil aktual/commit/timestamp/denominator,
bukan menganggap seluruh dokumen naratif yang ada selalu mutakhir.

source_manifest.json mengikat **source yang dipakai paket konteks**, bukan
menyatakan semua source telah diukur pada 4877fc7. Historical source commits dalam
JSON tetap harus dipertahankan. Mengubah tampilan/spasi/CRLF pada hasil raw bukan
syarat laporan; kegagalan/attempt/repair history tetap merupakan bagian provenance.
