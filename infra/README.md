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
