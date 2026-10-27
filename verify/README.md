# Verifikasi kebocoran baseline

Gunakan Python 3.11 dan dependensi `verify/requirements.txt`. Venv scanner yang
sudah ada juga memenuhi dependensi ini. Perintah berikut **tidak menjalankan
benchmark**, tidak membuat/restore DB, dan hanya SELECT baseline melalui bench_user.

```powershell
$env:DPR_PRIVATE_DIR = 'C:\dev\dpr-private'
$cVerifyCredential = Import-Clixml -LiteralPath (Join-Path $env:DPR_PRIVATE_DIR 'bench_user.credential.xml')
$env:BENCH_DATABASE_URL = 'postgresql://bench_user:' + [Uri]::EscapeDataString($cVerifyCredential.GetNetworkCredential().Password) + '@127.0.0.1:5433/baseline_1m?sslmode=disable'
try {
    .\scanner\.venv\Scripts\python.exe -m verify.leak_sim --artifact (Join-Path $env:DPR_PRIVATE_DIR 'baseline_1m.dump') --scenario baseline_dump --known-values (Join-Path $env:DPR_PRIVATE_DIR 'verify\baseline_1m_known.sqlite')
} finally {
    Remove-Item Env:BENCH_DATABASE_URL
    Remove-Variable cVerifyCredential
}
```

Credential XML itu DPAPI privat yang sudah dibuat sebelumnya, bukan file repo.
Untuk input credential baru tanpa password literal/history:

```powershell
$cVerifyPassword = Read-Host 'Password bench_user' -AsSecureString
$cVerifyCredential = [pscredential]::new('bench_user', $cVerifyPassword)
```

Tidak ada reset/password rotation otomatis. Jangan cetak credential/DSN. Snapshot
custom harus cocok hash generation evidence; pg_restore 18 di container hanya
mengeluarkan SQL ke handle privat, **tidak dieksekusi** dan tidak menghubungi DB.
Known-values SQLite berisi sel asli dan matching key acak; keduanya hanya di luar
repo. Berkas existing dipakai kembali hanya jika metadata/checksum sesuai. File
SQL ekspansi unik dibersihkan melalui finally, snapshot asli dan ledger dipertahankan.

Ringkasan: `evidence/leak/baseline_dump.json`, laporan engine scanner v1.2 pada
reservoir seragam 1.000 baris dari artefak yang sama di `baseline_dump_scanner/`,
`evidence/leakage/{baseline_dump,residual_before,protected_pending}.json`.
Tabel ringkas before/after ada di `evidence/leakage/before_after.csv` (after BELUM DIUJI).
Scanner dijalankan lewat engine Python bersama, bukan CLI dump yang membuat
ulang SQLite plaintext; semua baris artefak ikut agregasi residual k dan validasi.
Sampling tidak dipakai sebagai denominator ESCE/DIE/k. Lihat metodologi dan
batas pada NOTES.md; ini bukan scan S05/S06 repo/log/WAL atau pengujian protected.

Hitung ulang budget saja dari ledger dan evidence yang cocok:

```powershell
.\scanner\.venv\Scripts\python.exe -m verify.leakage_budget --known-values (Join-Path $env:DPR_PRIVATE_DIR 'verify\baseline_1m_known.sqlite')
.\scanner\.venv\Scripts\python.exe -m verify.output_audit --known-values (Join-Path $env:DPR_PRIVATE_DIR 'verify\baseline_1m_known.sqlite')
.\scanner\.venv\Scripts\python.exe -m pytest verify/tests -q
.\benchmark\.venv\Scripts\python.exe -m pytest benchmark/tests -q
```

Adapter profile membaca format kolom A (`columns.<name>.aead/domain/storage_column/bidx_column`).
File belum diintegrasikan berarti BELUM DIUJI. Skenario protected/backup tidak
menggunakan fallback baseline, tidak menerima decrypt tak terbatas, dan tetap
menunggu artefak serta hook OpenBao/toolkit nyata sebelum menghasilkan skor.
