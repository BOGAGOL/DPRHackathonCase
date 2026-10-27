# Modul C — survei Langkah 0

26 Oktober 2026 WIB · Delf · `feat/verify-bench`. Survei statis; arsip bukan acuan. Tanpa eksekusi kode/test/DB/benchmark; pekerjaan lama dipertahankan.

**a. Pemahaman tugas**

- C memiliki `datagen/`, `benchmark/`, `verify/`, `scanner/`, koordinasi docs/evidence; crypto/migrasi/backup produksi milik A.
- `postgres` hanya dibaca. Baseline baru: 734 sumber + 99.266 sintetis deterministik, mengikuti distribusi/format/keunikan/relasi/anomali; fixture test dibuat sendiri.
- Target di-commit sebelum benchmark; workload/kunci tetap, warmup, ≥3 run, median, raw samples, resource/storage/backup/restore. Migrasi menunggu baseline terekam.
- Evaluasi scanner v1.1 memakai ground truth independen dan label map, termasuk nama disamarkan; nyatakan in-sample.
- Ukur ESCE/DIE/ELS/DBR dan k-anonymity REF/age_band/pola NULL pada artefak nyata, tanpa kunci versus policy bocor.
- Setelah A/B siap: tamper/swap, role/API, rahasia/log, backup, benchmark B–P–P–B, indeks evidence, SBOM. Env saja, query berparameter, tanpa keluaran pribadi/rahasia; fungsi baru bertest, keputusan di NOTES.

**b–c. Inventaris dan usulan**

| Path | Isi, kesesuaian, dan tindakan |
| --- | --- |
| `sql/baseline/01_schema.sql` | 29 kolom + identity/indeks: **pakai ulang** di DB baru; pagar target wajib karena ada `DROP TABLE`. |
| `scripts/scale_lab.py` | Skema lab lama, tanpa distribusi sumber/seed, format berbeda: **buat baru** datagen. |
| `scripts/benchmark.py` | Raw/median/3 repeat tersedia, tetapi concurrency 1, 80/20, native PG17/skema lama: **adaptasi konsep**, runner tujuh workload/Docker/CSV baru. |
| `scripts/backup.py`, `tests/test_backup.py` | Dump memori/AES-GCM/drill, belum streaming/manifest-HMAC/retensi: **adaptasi subprocess/env** baseline; protected milik A. |
| `scripts/verify_security.py`, `tests/test_{api_security,crypto_import}.py` | Canary/grant/API/crypto lab: **adaptasi kasus**, runner kontrak/leakage/riwayat/log **baru**. |
| `scanner/`, `results/scanner/before_v1/` | Kode v1.1/test tersedia, hasil hanya v1.0/734: **pakai ulang**, run baru; **adaptasi** evaluator tanpa label map. Ground truth/metodologi Alby tidak ditemukan; template hanya header. |
| `evidence/{benchmark,benchmark-scaled,backup-restore,postgres-security}.json`, `security-tests.xml`, `dependencies.json` | Bukti historis lab 734/10k, bukan kontrak baru; dependensi bukan SBOM: **pertahankan**, buat evidence baru. |
| `docs/legacy-md_zhafif/{docs/PERFORMANCE.md,docs/OPERATIONS.md,PROGRESS.md}` | Menjelaskan batas lab/TLS/Transit belum diuji: **referensi survei saja**. |
| `datagen/`, `benchmark/`, `verify/`, `docs/{targets,evidence_index}.md` | Belum ada: **buat baru**. README campuran lab/scanner: hanya tambah panduan. `docs/MAIN_INVENTORY.md` lokal dipertahankan. |

**d. Urutan setelah persetujuan — berhenti setelah setiap langkah**

1. `docs/targets.md`: target prompt C, batas DB/API dan metode; commit/hash sebelum benchmark.
2. Datagen `baseline_100k`: seed 42, COPY/ANALYZE, validasi/checksum/snapshot.
3. Tujuh workload baseline: 3 run × 60 detik, concurrency 8, warmup 10 detik; backup/restore 3 run, DB sementara, validasi count. API plain menunggu B.
4. Scanner v1.1: direktori baru, evaluate dengan label map, regex-only dan nama disamarkan.
5. `leak_sim` + `leakage_budget` + residual k-anonymity baseline; sisanya menunggu A/B.

Setiap langkah: test, JSON/CSV, NOTES, ringkasan/perintah verifikasi; lalu berhenti.

**e. Kebutuhan dan pengisian env (jalankan kelak, bukan Langkah 0)**

Perlu role dari A/admin: generator CREATEDB/SELECT sumber, owner baseline/restore; bench SELECT/INSERT/UPDATE tanpa DDL; scanner SELECT-only. Isi env sesi berikut tanpa password di history/chat:

```powershell
Set-Location C:\dev\juara1onno
$cSpecs = @(@('DATAGEN_DATABASE_URL','postgres'),
            @('BENCH_DATABASE_URL','baseline_100k'),
            @('SCANNER_DATABASE_URL','postgres'))
foreach ($cSpec in $cSpecs) {
  $cUser = Read-Host ('Role untuk ' + $cSpec[0])
  $cSecure = Read-Host ('Password ' + $cUser) -AsSecureString
  $cCred = [pscredential]::new($cUser, $cSecure)
  try {
    $cUrl = 'postgresql://' + [Uri]::EscapeDataString($cUser) + ':' +
      [Uri]::EscapeDataString($cCred.GetNetworkCredential().Password) +
      '@127.0.0.1:5433/' + $cSpec[1]
    [Environment]::SetEnvironmentVariable($cSpec[0], $cUrl, 'Process')
  } finally { Remove-Variable cCred,cSecure,cUrl -ErrorAction SilentlyContinue }
}
# Setelah sesi: bersihkan ketiga env dengan Remove-Item Env:<nama>.
```

Opsional: `DATAGEN_TEST_DATABASE_URL` untuk DB uji terpisah. Kelak perlu OpenBao URL/CA/token terbatas; pg tools memakai env child, bukan argumen.

**f. Keputusan/ketidakjelasan untuk dikonfirmasi**

- Lokasi ground truth/metodologi Alby? Acuan independen tidak dibuat sendiri.
- Usulan: evidence utama `evidence/<kategori>/` mengikuti AGENTS; `results/bench/` lokal mengikuti prompt lama. Tentukan lokasi terbatas luar repo untuk keys/known-values/snapshot plaintext.
- Konfirmasi nama/hak role dan koneksi owner generator untuk restore. Scanner berpindah dari `postgres` ke baseline setelah grant tersedia.
- Validasi membedakan 734 sumber dan tambahan; anomali mengikuti proporsi sumber. Sepakati aturan `age_band` dengan A sebelum perbandingan residual.
