# Benchmark DB — baseline dan protected

**Status 29 Oktober 2026:** hasil DB B-P-P-B naive dan v2 pada 100k/1M sudah ada
pada `evidence/benchmark/bppb_*` dan `bppb_v2_*`, termasuk raw, median, resource
serta target comparison. Semua skenario DB gagal target latensi/throughput
P01/P01A/P02; P03 error-rate lulus. Jangan mengganti target atau menghapus hasil gagal.
Benchmark API mempunyai [runbook/status terpisah](api/README.md); percobaan setup
bukan hasil pengukuran API. Demo 734 tidak menjalankan benchmark otomatis.

Untuk setup/reproduksi awal gunakan [panduan utama](../docs/operations/REPRODUCTION.md).
Bagian berikut mempertahankan perintah per sesi dan prasyarat operasional. Jangan
menjalankan ulang output existing; gunakan sesi baru yang disetujui pemilik benchmark.

## Baseline awal — PowerShell

Jalankan dari root repo, pg-dpr sudah berjalan. Ini sesi DB plain; jangan menjalankan
migrasi, aplikasi/demo, test berat atau container lain selama measurement berlangsung.

```powershell
python -m venv benchmark/.venv
.\benchmark\.venv\Scripts\python.exe -m pip install -r benchmark/requirements.txt
.\benchmark\.venv\Scripts\python.exe -m pytest benchmark/tests datagen/tests -q
$env:DPR_PRIVATE_DIR = 'C:\dev\dpr-private'
$cBenchCred = Import-Clixml "$env:DPR_PRIVATE_DIR\bench_user.credential.xml"
$cAdminSecure = Read-Host 'Password admin postgres lab (CREATE/restore/maintenance)' -AsSecureString
$cAdminCred = [pscredential]::new('postgres',$cAdminSecure)
try {
  $env:BENCH_DATABASE_URL = 'postgresql://bench_user:' +
    [Uri]::EscapeDataString($cBenchCred.GetNetworkCredential().Password) +
    '@127.0.0.1:5433/baseline_100k'
  $env:DATAGEN_DATABASE_URL = 'postgresql://postgres:' +
    [Uri]::EscapeDataString($cAdminCred.GetNetworkCredential().Password) +
    '@127.0.0.1:5433/postgres'
  .\benchmark\.venv\Scripts\python.exe -m benchmark run --db baseline_100k --label before --adapter plain --scenario all --runs 3 --duration 60 --concurrency 8 --warmup 10
  if ($LASTEXITCODE -ne 0) { throw 'Benchmark gagal; raw dipertahankan, lihat evidence agregat' }
  .\benchmark\.venv\Scripts\python.exe -m benchmark backup-restore --db baseline_100k --label before --runs 3
  if ($LASTEXITCODE -ne 0) { throw 'Backup/restore gagal; lihat evidence agregat' }
} finally {
  Remove-Item Env:BENCH_DATABASE_URL,Env:DATAGEN_DATABASE_URL -ErrorAction SilentlyContinue
  Remove-Variable cBenchCred,cAdminCred,cAdminSecure -ErrorAction SilentlyContinue
}
Import-Csv evidence/benchmark/baseline/summary.csv | Format-Table -AutoSize
Get-Content -Raw evidence/benchmark/baseline/backup_restore.json | ConvertFrom-Json
```

Jika credential XML tidak tersedia, gunakan `Read-Host -AsSecureString` dan
`[pscredential]::new('bench_user', ...)` untuk password bench yang sudah ditetapkan.
Jangan mencetak credential/DSN atau isi direktori privat.

Sesi yang sudah mempunyai env.json atau CSV backup ditolak agar hasil lama tidak
tertimpa. Sebelum pengulangan sesi, arsipkan raw/evidence secara terpisah setelah
ditinjau; jangan menghapus hasil gagal atau mencampur sesi awal dan B–P–P–B.
Metodologi, keputusan instance, sumber utilitas dan batas ada di [NOTES.md](NOTES.md).

## Sesi utama 1M dan pemeriksaan silang

Dengan env aman yang sama, pilihan DB menentukan koneksi dan keluaran secara eksplisit.
Korpus 1M terpisah di DPR_PRIVATE_DIR; hasil 100k tetap utuh. Disk host wajib >=10 GB
sebelum 1M dan diperiksa lagi sebelum setiap run/restore. Jalankan sekali; sesi yang
sudah ada ditolak. Raw dapat dikompres gzip setelah semua pengukuran sesi selesai.

```powershell
.\benchmark\.venv\Scripts\python.exe -m benchmark run --db baseline_1m --label before --adapter plain --scenario all --runs 3 --duration 60 --concurrency 8 --warmup 10
.\benchmark\.venv\Scripts\python.exe -m benchmark backup-restore --db baseline_1m --label before --runs 3
# Dilakukan sesudah sesi 1M/restore, memakai corpus 100k yang telah disimpan:
.\benchmark\.venv\Scripts\python.exe -c "from benchmark.pgbench_crosscheck import crosscheck; crosscheck()"
Import-Csv evidence/benchmark/baseline_1m/summary.csv | Format-Table -AutoSize
Get-Content -Raw evidence/benchmark/crosscheck_pgbench.json | ConvertFrom-Json
```

Keluaran 1M: results/bench/before_1m/ dan evidence/benchmark/baseline_1m/.
Pgbench memakai custom script via stdin; kunci tidak masuk argv/repo. Tidak ada
inisialisasi pgbench atau tabel baru pada baseline. Raw transaksi tanpa kunci berada
di results/bench/crosscheck_pgbench/; file sementara container dibersihkan setelah disalin.
## Audit gangguan daya dari hasil yang sudah ada

```powershell
.\benchmark\inspect_power_events.ps1
.\benchmark\.venv\Scripts\python.exe -m benchmark.power_incident
.\benchmark\.venv\Scripts\python.exe -m pytest benchmark/tests/test_power_incident.py -q
```

Khusus audit retrospektif 27 Oktober 2026: membaca System/Kernel-Power dan raw
resource/log pgbench lokal yang sudah ada, lalu menambahkan kualifikasi metadata.
Tidak menjalankan workload, query DB, backup/restore, atau start/stop container.
Perintah terakhir hanya unit test analisis dengan fixture sintetis. Hasil:
`evidence/benchmark/baseline_1m/power_events.json`, `power_incident.json`,
`power_run_timeline.csv`. Lihat NOTES.md untuk interval baterai yang terkonfirmasi
dan batas penilaian dampak. File raw harus tersedia di mesin yang menjalankan audit.

## Pengukuran pengganti yang diotorisasi setelah gangguan baterai

Dengan BENCH_DATABASE_URL, DATAGEN_DATABASE_URL, DPR_PRIVATE_DIR sudah diatur
seperti di atas, charger terpasang dan hanya pg-dpr berjalan:

```powershell
.\benchmark\.venv\Scripts\python.exe -m benchmark.replacement_ac
```

Hanya backup/restore baseline_1m 3 run dan pgbench baseline_100k 3 run yang
dijalankan. Workload21 run tidak dipanggil. Setiap panggilan membuat sesi
ac_<UTC> eksklusif; jangan mengulang perintah tanpa otorisasi pengukuran baru.
Ringkasan canonical diperbarui hanya setelah verifikasi AC + integritas lulus;
hasil lama disalin byte-identik ke history dengan label "terdampak baterai".
Raw lama tidak dipindah/dihapus. Lihat active_measurements.json untuk pilihan
hasil aktif dan power_verification.json pada folder sesi untuk bukti AC.
# Adapter protected dan gerbang kebenaran (28 Oktober 2026)

Instal dependensi modul dan toolkit publik A dari root repo:

```powershell
.\.venv\Scripts\python.exe -m pip install -r benchmark/requirements.txt -e ./toolkit
.\.venv\Scripts\python.exe -m benchmark.parity
.\.venv\Scripts\python.exe -m benchmark.compare --before <summary-B.json> --after <summary-P.json> --out results/bench/compare
# Alias: python -m benchmark compare --before ... --after ... --out ...
```

Parity membutuhkan `DPR_PRIVATE_DIR`, `BENCH_DATABASE_URL` (bench_user, baseline,
tanpa TLS), `PROTECTED_DATABASE_URL` (app_user, verify-full + CA),
`BENCH_MONITOR_DATABASE_URL` (admin/monitoring terpisah, verify-full, database
dengan view pg_stat_statements), dan `OPENBAO_ADDR`/`OPENBAO_CACERT`/
`OPENBAO_TOKEN` svc-app aktif. Muat password/token dari material privat ke env;
jangan menulis DSN berpassword di command line/history. Tidak memberikan hak
monitoring ke role workload. `benchmark.parity` melakukan setup scope sementara
melalui koneksi admin dan membersihkannya; database anggota baseline/protected
tidak diubah permanen. Scope/audit setup berada di protected, tidak di baseline.

Adapter mengembalikan bisnis sama dengan plain; list membuka nama saja. DEK
tidak dicache antarrequest, UUID internal selalu dipakai untuk AAD. Monitor
opsional pada `runner.one_run(..., db_monitor=...)` mengambil counter sebelum
dan sesudah fase measured, bukan request sinkron tambahan. db_time adalah mean
execution time, tidak menyediakan persentil. Compare mempertahankan penilaian
rasio dan absolut terpisah. Mixed memakai ambang tulis 10ms.

Gerbang parity adalah pemeriksaan terbatas 1000 kunci berbeda per skenario baca
per dataset, ditambah probe rollback tulis; bukan pengganti benchmark 3 run.
Perintah `benchmark run` lama tetap khusus baseline awal. Jangan menjalankannya
untuk membuat hasil after atau menimpa artefak historis; B-P-P-B membutuhkan
instruksi pengguna terpisah dan kondisi daya/perangkat yang memenuhi syarat.

Test komponen dijalankan terpisah untuk menghindari konflik basename test/conftest:

```powershell
.\.venv\Scripts\python.exe -m pytest benchmark/tests datagen/tests verify/tests -q
.\.venv\Scripts\python.exe -m pytest scanner/tests -q
```


## B-P-P-B resmi v2 terpisah dari sesi Codex

Memerlukan kredensial DPAPI yang sudah disimpan dan helper privat yang sudah digunakan di laptop ini. Helper membaca secret dari luar repo, tanpa argumen password. Jalankan sekali; output/worker yang ada ditolak.

```powershell
$env:DPR_OPENBAO_HTTP_TRANSPORT = 'https_pool'
$env:DPR_BENCH_DEK_CACHE_TTL = '0'
$env:DPR_BENCH_DEK_CACHE_ENTRIES = '0'
powershell -NoProfile -NonInteractive -File C:\dev\dpr-private\benchmark\bppb-launch.ps1 -m benchmark.paired_v2 preflight
if ($LASTEXITCODE -ne 0) { throw 'Gate awal gagal; benchmark tidak dimulai' }
.\benchmark\start_bppb_v2.ps1
```

Proses baru tersembunyi tetap berjalan setelah terminal/sesi agen selesai. Progres/log: results/bench/bppb_v2/runner.stdout.log; jangan menampilkan env atau isi secret. Cek paling sering15menit. Worker menyimpan setiap run, menyusun perbandingan versi dan memverifikasi lima DB, kemudian commit+push hasil ke branch perf/keyservice-latency. Receipt status/hash di results/bench/bppb_v2/publication.json. Tidak merge main.
