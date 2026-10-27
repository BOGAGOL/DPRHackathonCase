# Benchmark baseline awal — PowerShell

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
