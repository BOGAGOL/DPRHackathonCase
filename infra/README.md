# Infra Tahap 1 (Windows / PowerShell)

Jalankan dari root repo. Python 3.11+ dan Docker Desktop (Linux containers).
Jangan jalankan Compose referensi buku untuk quick-start ini.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r infra/requirements.txt
# Direktori khusus di luar checkout; jangan memakai direktori berisi file lain.
$env:DPR_SECRETS_DIR = Join-Path $env:LOCALAPPDATA 'DPR\crypto-infra-tls'
.\.venv\Scripts\python.exe -m infra.tls.make_ca
docker compose -f infra/compose.yaml up -d openbao
$env:OPENBAO_ADDR = 'https://127.0.0.1:8200'
$env:OPENBAO_CACERT = Join-Path $env:DPR_SECRETS_DIR 'tls\ca.crt'
```

OpenBao belum healthy sampai di-init dan di-unseal secara manual. Jangan memakai
`--wait` pada start pertama. CA root tidak perlu diinstal ke trust store Windows;
client menggunakan file CA eksplisit. File CA key tidak dipasang ke server.

```powershell
.\.venv\Scripts\python.exe -m infra.openbao.init status
.\.venv\Scripts\python.exe -m infra.openbao.init init
# 3 shares, threshold 2. Dua kustodian memasukkan satu share per pemanggilan:
.\.venv\Scripts\python.exe -m infra.openbao.init unseal
.\.venv\Scripts\python.exe -m infra.openbao.init unseal
# Root HANYA pada sesi bootstrap admin. Tidak menampilkan token ke terminal.
$material = Get-Content -LiteralPath (Join-Path $env:DPR_SECRETS_DIR 'openbao\init-material.json') -Raw | ConvertFrom-Json
$env:OPENBAO_TOKEN = $material.root_token
$material = $null
try {
  .\.venv\Scripts\python.exe -m infra.openbao.init configure
  .\.venv\Scripts\python.exe -m infra.openbao.init issue --ttl-seconds 3600
} finally {
  Remove-Item Env:OPENBAO_TOKEN -ErrorAction SilentlyContinue
}
```

**Peringatan:** init-material.json menyimpan root token dan ketiga shares bersama
untuk bootstrap lab. Pindahkan shares ke kustodian berbeda dan root ke penyimpanan
offline. Salinan gabungan adalah risiko sampai pemisahan selesai. Jangan kirim isi
file ke chat, Git, log, screenshot atau environment aplikasi. Init tidak menimpa
material lama, tidak mencetak material, dan tidak otomatis unseal.

Token diterbitkan per policy dalam `openbao/tokens/<policy>-<timestamp>.json`
di direktori eksternal. TTL default 1 jam, rentang 1 menit–4 jam, tidak renewable,
tanpa default policy. Baca token policy yang dibutuhkan langsung ke env proses
workload (contoh PowerShell, tanpa menampilkan nilainya):

```powershell
$file = Get-ChildItem -LiteralPath (Join-Path $env:DPR_SECRETS_DIR 'openbao\tokens') -Filter 'svc-migration-*.json' | Sort-Object Name | Select-Object -Last 1
$env:OPENBAO_TOKEN = (Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json).auth.client_token
# ... migrasi pada tahap berikutnya ...
.\.venv\Scripts\python.exe -m infra.openbao.init revoke-migration
Remove-Item Env:OPENBAO_TOKEN
```

`configure` aman dipanggil ulang untuk policy/key yang cocok (tidak merotasi key).
`issue` membuat token baru; lakukan hanya bila diperlukan dan cabut token lama.
Token orphan agar revokasi root bootstrap tidak mencabut workload, tetapi expiry
tetap membatasi umur token. AppRole/agent belum termasuk tahap ini: operator harus
menerbitkan ulang sebelum TTL habis. Setelah restart server, ulangi unseal manual.
File recovery kosong setelah interupsi harus ditangani operator; jangan menghapus
file lalu mengulang init tanpa mengecek status/recovery terlebih dahulu.

PostgreSQL: pakai `pg-dpr` yang sudah ada di 5433 tanpa mengubah database `postgres`,
atau jalankan instance **baru** pada port default 5434:

```powershell
# Isi DPR_POSTGRES_PASSWORD dari secret manager / environment sesi; jangan literal
# password dalam command history. Image akan menolak password kosong.
docker compose -f infra/compose.yaml --profile new-postgres up -d postgres
```

Database baru bernama `dpr_lab`, admin `dpr_bootstrap`, volume PG18 terpisah.
Port PostgreSQL hanya loopback; TLS PostgreSQL belum termasuk tahap ini.
Lihat [NOTES.md](NOTES.md) untuk keputusan dan batas klaim.

```powershell
.\.venv\Scripts\python.exe -m pytest infra/tests -q
```
