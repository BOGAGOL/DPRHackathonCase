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
# Verifikasi artefak protected (28 Oktober 2026)

```powershell
.\.venv\Scripts\python.exe -m pip install -r verify/requirements.txt -e ./toolkit
.\.venv\Scripts\python.exe -m verify.leak_sim --db protected_100k --artifact <dump-privat> --known-values <ledger-baseline-100k-privat> --scenario protected_dump_no_key
# Skenario lain: protected_dump_with_pii_key / protected_dump_with_finance_key / protected_dump_with_search_key
# Ukuran utama: --db protected_1m dengan artefak/ledger 1M yang cocok.
.\.venv\Scripts\python.exe -m verify.after_comparison
```

Setiap skenario berjalan pada proses tersendiri. No-key tidak membuat client
dekripsi dan tidak membaca token. Untuk skenario dengan kemampuan kunci, operator
menyediakan token terbatas `DPR_LEAK_TOKEN` dengan tepat satu policy khusus C:
`modc-leak-pii` hanya decrypt pii-kek, `modc-leak-finance` hanya decrypt finance-kek,
atau `modc-leak-search` hanya HMAC search-hmac; semuanya boleh lookup-self dan
revoke-self, tanpa default/root policy, TTL maksimal 4 jam. Semua koneksi OpenBao
HTTPS + CA eksplisit dari `OPENBAO_ADDR`/`OPENBAO_CACERT`. Jangan memakai svc-app
untuk meniru kebocoran satu domain: svc-app memiliki kedua kemampuan decrypt.
Policy aplikasi/toolkit A tidak diubah; client simulasi memeriksa identitas ACL
khusus dan memakai format AES-GCM/AAD toolkit A yang sama. Probe decrypt domain
terlarang harus ditolak. Operator mencabut token simulasi setelah skenario.

Dump custom, SQL hasil ekspansi, ledger dan rahasia hanya di DPR_PRIVATE_DIR
di luar repo. Input dump dibaca tanpa menjalankan SQL; COPY anggota_protected
divalidasi lengkap, NULL/populasi/legacy ID diverifikasi terhadap ledger privat
dengan lookup batch. ESCE/DIE berisi numerator/denominator, ELS histogram tanpa
nilai grup, DBR daftar kolom/domain langsung pulih. K-anonymity memakai REF,
age_band nyata dan pola NULL pada seluruh populasi dan subset sumber/sintetis.

Uji search memakai seluruh nilai baseline sebagai kamus sintetis lengkap untuk
mengukur batas atas serangan dictionary berkemampuan HMAC, bukan asumsi bahwa
penyerang nyata mengetahui seluruh baseline. ESCE menghitung pemulihan langsung;
inferensi antarkolom tidak ditambahkan diam-diam. Dump logis tidak membuktikan
keamanan file fisik/WAL atau log operasional. Evidence before historis diarsipkan
sebelum tabel comparison diperbarui; tidak menjalankan benchmark performa.
