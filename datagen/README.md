# Datagen Modul C — PowerShell

Jalankan dari `C:\dev\juara1onno`. Aktifkan Docker Desktop dan `pg-dpr` yang sudah ada;
jangan membuat ulang container/volume. PostgreSQL harus 18; pg_dump lokal 17 tidak dipakai.

```powershell
python -m venv datagen/.venv
.\datagen\.venv\Scripts\python.exe -m pip install -r datagen/requirements.txt
docker start pg-dpr
$env:DPR_PRIVATE_DIR = 'C:\dev\dpr-private'

$cAdminSecure = Read-Host 'Password admin postgres lab' -AsSecureString
$cAdminCred = [pscredential]::new('postgres', $cAdminSecure)
try {
  $env:DATAGEN_DATABASE_URL = 'postgresql://postgres:' +
    [Uri]::EscapeDataString($cAdminCred.GetNetworkCredential().Password) +
    '@127.0.0.1:5433/postgres'
} finally { Remove-Variable cAdminCred,cAdminSecure }

.\datagen\.venv\Scripts\python.exe -m pytest datagen/tests -q
# Jalankan GENERATE hanya sekali; target yang sudah ada ditolak tanpa diubah:
.\datagen\.venv\Scripts\python.exe -m datagen --rows 100000 --seed 42 --target-db baseline_100k
.\datagen\.venv\Scripts\python.exe -m datagen validate --db baseline_100k --rows 100000
.\datagen\.venv\Scripts\python.exe -m datagen snapshot --db baseline_100k --out "$env:DPR_PRIVATE_DIR\baseline_100k.dump"
```

Jika baseline/snapshot sudah dibuat pada sesi ini, cukup **validate**, jangan ulang generate/snapshot.
`DPR_PRIVATE_DIR` harus berada di luar repo dan akses NTFS dibatasi untuk pemilik lab.
Provision benchmark memakai password baru melalui prompt atau credential lab tersimpan:

```powershell
# Pilihan A: password bench yang ditetapkan pemilik lab (role baru saja):
$cBenchSecure = Read-Host 'Password bench_user lab' -AsSecureString
$cBenchCred = [pscredential]::new('bench_user', $cBenchSecure)
# Pilihan B untuk sesi lab yang credential-nya telah dibuat agen:
# $cBenchCred = Import-Clixml "$env:DPR_PRIVATE_DIR\bench_user.credential.xml"
try {
  $env:BENCH_DATABASE_URL = 'postgresql://bench_user:' +
    [Uri]::EscapeDataString($cBenchCred.GetNetworkCredential().Password) +
    '@127.0.0.1:5433/baseline_100k'
} finally { Remove-Variable cBenchCred,cBenchSecure -ErrorAction SilentlyContinue }
.\datagen\.venv\Scripts\python.exe -m datagen provision --db baseline_100k

Get-Content -Encoding UTF8 evidence/targets_commit.json
$cDataset = Get-Content -Raw -Encoding UTF8 evidence/datasets/baseline_100k.json | ConvertFrom-Json
$cDataset.validation
$cDataset.roles
$cDataset.snapshot
# Setelah selesai menggunakan sesi:
Remove-Item Env:DATAGEN_DATABASE_URL,Env:BENCH_DATABASE_URL -ErrorAction SilentlyContinue
```

`provision` mengautentikasi bench_user dan memeriksa grant, tidak merotasi password role lama.
Scanner memakai credential scanner yang sudah ada; cukup arahkan `SCANNER_DATABASE_URL` ke baseline
saat langkah scanner nanti. Jangan mencetak variabel DSN atau membaca isi file privat ke output.
Keputusan distribusi/anomali/keamanan dan batas CONNECT PUBLIC ada di [NOTES.md](NOTES.md).

## Dataset utama 1M — amandemen tim 27 Oktober 2026

`baseline_1m` berisi 1.000.000 baris (734 sumber + 999.266 tambahan), seed 42.
`baseline_100k` beserta hasil benchmark awal tetap dipertahankan sebagai titik skala
dan jaring pengaman. Kedua database berada di `pg-dpr`; database sumber `postgres`
hanya dibaca. Gunakan penyiapan env admin/bench di atas dengan credential yang sama;
`--db` memilih database baseline secara eksplisit, bukan database sumber.

```powershell
$env:DPR_PRIVATE_DIR = 'C:\dev\dpr-private'
# Referensi pembuatan sekali saja; jangan ulangi bila DB/snapshot sudah ada:
# .\datagen\.venv\Scripts\python.exe -m datagen --rows 1000000 --seed 42 --target-db baseline_1m
# .\datagen\.venv\Scripts\python.exe -m datagen provision --db baseline_1m
# .\datagen\.venv\Scripts\python.exe -m datagen snapshot --db baseline_1m --out "$env:DPR_PRIVATE_DIR\baseline_1m.dump"

# Pemeriksaan ulang (memerlukan DATAGEN_DATABASE_URL dari penyiapan aman di atas):
.\datagen\.venv\Scripts\python.exe -m datagen validate --db baseline_1m --rows 1000000
Get-Content -Raw -Encoding UTF8 evidence/datasets/baseline_1m.json | ConvertFrom-Json
Get-Content -Raw -Encoding UTF8 evidence/datasets/baseline_1m_execution.json | ConvertFrom-Json
Get-Item -LiteralPath "$env:DPR_PRIVATE_DIR\baseline_1m.dump" | Select-Object Name,Length
Get-PSDrive C | Select-Object Name,Free
```

Metadata execution memisahkan durasi generation (termasuk validasi bawaan), validasi ulang,
provision, snapshot, dan total; mencatat ukuran DB/tabel/indeks serta sisa disk host dan
filesystem Docker. Kapasitas virtual Docker tidak menggantikan batas ruang fisik Windows.
Snapshot tetap di luar repo, dicek header/checksum dan `pg_restore --list`; ini belum
merupakan drill restore 1M. Benchmark 1M menunggu instruksi terpisah.
