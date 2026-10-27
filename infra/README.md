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
  if ($LASTEXITCODE -ne 0) { throw 'Konfigurasi OpenBao gagal; jangan menerbitkan token.' }
  .\.venv\Scripts\python.exe -m infra.openbao.init issue --ttl-seconds 3600
  if ($LASTEXITCODE -ne 0) { throw 'Penerbitan token gagal; periksa material eksternal.' }
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

Keputusan database proyek (27 Oktober 2026): semua database berada pada container
**`pg-dpr`, PostgreSQL 18, port host 5433**. OpenBao tetap Compose ini pada 8200.
Compose ini hanya mengelola OpenBao. Target mesin ada di
[database-targets.json](database-targets.json); panduan TLS in-place ada di
[postgres/README.md](postgres/README.md).

```powershell
# Jalankan pada Docker context yang memiliki container/data tersebut.
docker start pg-dpr
.\.venv\Scripts\python.exe -m infra.postgres.make_cert
.\.venv\Scripts\python.exe -m infra.postgres.enable_tls inspect
.\.venv\Scripts\python.exe -m infra.postgres.enable_tls apply
```

`baseline_100k` yang sudah ada dipertahankan untuk MODE=plain; target MODE=protected
adalah `protected_734` / `protected_100k`. Skrip TLS tidak membuat database/tabel,
tidak recreate/restart container, dan tidak menjalankan migrasi. Sertifikat dan
key server dipasang di volume data yang sudah ada, lalu ALTER SYSTEM + reload.
Snapshot rollback dan CA/key privat berada di DPR_SECRETS_DIR di luar repo.
Client memakai `sslmode=verify-full` dan CA yang sama.
Klarifikasi: instance benchmark resmi berada di laptop teman; laptop ini memakai
clone development pg-dpr sendiri. Clone dan validasinya disiapkan dengan
`python -m infra.postgres.development ...`, detail di panduan PostgreSQL di atas.
Evidence development terpisah dari evidence/datasets resmi.

```powershell
.\.venv\Scripts\python.exe -m pytest infra/tests -q
```

Uji container nyata (Docker aktif, image PostgreSQL 18/OpenBao akan diunduh bila
belum ada). Uji membuat project/volume acak, memakai data sintetis dalam memori,
lalu menghapus hanya resource uji tersebut. Tidak menyentuh `pg-dpr` atau volume
`dpr-infra`. Recovery material uji berada di temporary directory di luar repo.
PostgreSQL disposable hanya didefinisikan di `infra/tests/compose.postgres.yaml`,
tanpa port tetap. Ini fixture test, bukan pilihan database proyek.

```powershell
$env:DPR_INFRA_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m pytest infra/tests/test_integration.py -q
Remove-Item Env:DPR_INFRA_INTEGRATION
```

Hasil mesin ke `evidence/infra/integration.json`: AAD cocok/salah/hilang, ACL,
TTL, revokasi, rotate/rewrap/config, TLS/CA, restart + unseal ulang, PostgreSQL 18.

Untuk memeriksa OpenBao lab yang sudah di-bootstrap, muat empat token workload
terbaru ke env verifikasi (tidak memakai root):

```powershell
$policies = 'svc-app', 'svc-migration', 'svc-verify', 'key-operator'
try {
  foreach ($policy in $policies) {
    $file = Get-ChildItem -LiteralPath (Join-Path $env:DPR_SECRETS_DIR 'openbao\tokens') -Filter "$policy-*.json" | Sort-Object Name | Select-Object -Last 1
    $name = 'OPENBAO_' + $policy.ToUpper().Replace('-', '_') + '_TOKEN'
    [Environment]::SetEnvironmentVariable($name, (Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json).auth.client_token, 'Process')
  }
  .\.venv\Scripts\python.exe -m infra.openbao.verify
} finally {
  foreach ($policy in $policies) {
    $name = 'OPENBAO_' + $policy.ToUpper().Replace('-', '_') + '_TOKEN'
    [Environment]::SetEnvironmentVariable($name, $null, 'Process')
  }
}
```

Verifier menulis `evidence/infra/openbao.json` dan exit nonzero saat gagal.
Verifier membuat ciphertext/datakey/HMAC sintetis dan rewrap, tanpa rotasi key
lab. Uji rotasi/config sebenarnya hanya dijalankan di container disposable.
Jalankan sebelum mencabut token migrasi; token kadaluarsa memerlukan penerbitan
ulang manual. Materi rahasia tidak ditulis ke evidence.
