# Backup / restore tahap 5

Jalankan dari root repo dengan Python venv (`python -m pip install -r infra/requirements.txt`
dan `python -m pip install -e toolkit`). Tidak perlu paket Python tambahan.
Gunakan PostgreSQL **18** di `pg-dpr`, port host **5433**, dengan TLS verify-full.
Tidak membuat ulang container. Pilihan sumber: `protected_734`, `protected_100k`,
`protected_1m`; jumlah record tidak di-hardcode. Dataset 1m harus dimigrasikan dahulu.

## Environment (isi melalui pengelola rahasia, bukan literal di history)

| Variable | Isi |
|---|---|
| `PGHOST`, `PGPORT` | Default `127.0.0.1`, `5433` |
| `PGSSLROOTCERT` | Path CA PostgreSQL di host |
| `DPR_BACKUP_PASSWORD` | Password `backup_user` |
| `DPR_RESTORE_USER`, `DPR_RESTORE_PASSWORD` | Akun operator restore; default username `postgres` |
| `DPR_BACKUP_KEY_B64` | 32 byte CSPRNG, Base64; khusus enkripsi backup |
| `DPR_BACKUP_HMAC_KEY_B64` | 32 byte CSPRNG **berbeda**; khusus HMAC manifest |
| `DPR_BACKUP_DIR` | Folder khusus, absolut, di luar repo |
| `OPENBAO_ADDR`, `OPENBAO_CACERT`, `OPENBAO_VALIDATION_TOKEN` | Hanya untuk `--with-openbao` dan `retention-test`; token TTL terbatas policy `svc-app` |

Password/kunci tidak memiliki opsi CLI. Jangan gunakan connection URL berisi password.
`backup_user` tidak memerlukan kredensial OpenBao. Proses pg_dump/pg_restore diberi
environment PostgreSQL saja; token dan kunci backup tidak diteruskan ke container.
Docker hanya menyalin **CA publik**, lalu menghapusnya; tidak menyalin dump atau private key.
Role database harus sudah tersedia sesuai tahap 3. Dump ini tidak berisi global role/password;
pada cluster pengganti, operator harus bootstrap role lebih dulu dengan password baru.

## Windows lokal yang sudah menjalankan tahap 1–4

`--local-credentials` adalah pilihan eksplisit untuk memuat kredensial DPAPI yang
sudah ada di laptop operator. Helper memuatnya ke memori/environment, tidak ke argv.
`init-keys` membuat dua kunci baru, menyimpannya dengan DPAPI di luar Git, dan
mempertahankan kunci yang sudah ada. **Jangan mengganti kunci untuk backup lama.**

```powershell
$env:DPR_SECRETS_DIR = Join-Path $env:LOCALAPPDATA 'DPR\crypto-infra-tls'
$env:DPR_BACKUP_DIR = Join-Path $env:LOCALAPPDATA 'DPR\encrypted-backups'
python -m scripts.backup init-keys
python -m scripts.backup --local-credentials backup --source protected_734
python -m scripts.backup --local-credentials backup --source protected_100k
# Jika sudah dimigrasikan:
python -m scripts.backup --local-credentials backup --source protected_1m
```

Output JSON menunjuk manifest dan artifact id; artefak terenkripsi tetap di luar repo.
Tetapkan `$manifest` ke path manifest yang dihasilkan (path ini bukan rahasia).

```powershell
python -m scripts.backup --local-credentials restore --manifest $manifest
python -m scripts.backup --local-credentials restore --manifest $manifest --with-openbao
python -m scripts.backup --local-credentials tamper-test --manifest $manifest
python -m scripts.backup --local-credentials retention-test --manifest $manifest
```

Perintah pertama restore tidak menyentuh OpenBao, bahkan jika token ada di environment.
Perintah kedua membutuhkan OpenBao initialized + unsealed dan token `svc-app` yang
masih berlaku. Mengaktifkan container saja tidak membuka segel setelah restart.
Jangan memasukkan unseal key atau root token ke tool backup/restore.

Restore hanya membuat database baru bernama `dpr_restore_<UUID hex>`, tidak menimpa
`protected_*`, baseline, atau database `postgres`. Nama default tercetak di output
dan evidence; nama eksplisit melalui `--target` wajib mengikuti pola tersebut dan
belum ada. Database hasil restore **dipertahankan** untuk pemeriksaan operator.
Alih koneksi layanan ke nama database hasil restore setelah verifikasi dan koordinasi B.
Uji retensi membersihkan tiga database sementara yang dibuatnya sendiri.

## Bukti dan benchmark

| Perintah | Laporan default |
|---|---|
| `init-keys` | `evidence/backup/key-setup.json` |
| `backup` | `evidence/backup/backup-report.json` |
| `restore` | `evidence/backup/restore-report.json` |
| `tamper-test` | `evidence/backup/tamper.json` |
| `retention-test` | `evidence/backup/retention.json` |

Laporan berisi metadata/count/check saja, tanpa nilai anggota atau kunci.
`--evidence-dir` sebelum subcommand memisahkan hasil tiap dataset/run, contohnya:

```powershell
python -m scripts.backup --local-credentials --evidence-dir evidence/backup/100k/run1 backup --source protected_100k
python -m scripts.backup --local-credentials --evidence-dir evidence/backup/100k/run1 restore --manifest $manifest
```

Untuk benchmark ulang minimal tiga kali pada 734, 100k, dan 1m yang tersedia;
gunakan pasangan manifest per run. `backup_seconds`, `restore_seconds`, dan
`size_bytes` tersedia di laporan. Waktu mencakup koneksi TLS, proses streaming,
verifikasi integritas, dan validasi; restore juga menghitung autentikasi seluruh
artefak sebelum membuat DB. Catat mode smoke test karena memengaruhi waktu.
Jangan menganggap uji laptop pengembang sebagai benchmark resmi tiga pengulangan.
Sediakan ruang untuk arsip, database hasil restore dan WAL; retensi memerlukan
hingga tiga salinan DB. Pilih 734 untuk demonstrasi retensi jika disk terbatas.

## Test

```powershell
python -m pytest scripts/backup/tests -q
$env:DPR_BACKUP_INTEGRATION = '1'
python -m pytest scripts/backup/tests -q
Remove-Item Env:DPR_BACKUP_INTEGRATION
```

Integration memakai PG18 + OpenBao TLS pada project Docker acak, data sintetis
buatan sendiri; volume project tersebut saja dihapus di teardown.
Evidence integration: `evidence/backup/integration.json`.
