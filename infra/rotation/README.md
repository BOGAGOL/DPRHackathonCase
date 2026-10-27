# Tahap 6: rotate / rewrap PII

Jalankan dari root repo dengan venv yang sudah dipakai tahap 1–5. Tidak perlu dependency
baru. Database tetap PG18 `pg-dpr` port host 5433, TLS verify-full. OpenBao initialized,
unsealed, HTTPS CA tepercaya. Format field/AAD/protection_version v1 tidak berubah.

## Persiapan akses

1. Operator DB menerapkan `sql/protected/03_rotation.sql` melalui perintah `prepare` di
   bawah. Tidak perlu membuat ulang container atau menjalankan ulang migrasi/provision.
2. Sediakan token finite-TTL policy `key-operator` sebagai `OPENBAO_KEY_OPERATOR_TOKEN`.
3. Sediakan token finite-TTL policy `svc-app` sebagai `OPENBAO_VALIDATION_TOKEN`.
4. Sediakan password `admin_user` dan `scanner_user` melalui environment. Gunakan
   jendela maintenance: hentikan insert/update anggota selama operasi dan hindari
   operator lain melakukan rotasi/config key secara bersamaan.

| Environment | Keterangan |
|---|---|
| `OPENBAO_ADDR`, `OPENBAO_CACERT` | HTTPS origin dan path CA host |
| `OPENBAO_KEY_OPERATOR_TOKEN` | Hanya policy `key-operator`; tidak bisa decrypt |
| `OPENBAO_VALIDATION_TOKEN` | Hanya policy `svc-app`; untuk validasi semua field |
| `PGHOST`, `PGPORT`, `PGSSLROOTCERT` | Default host 127.0.0.1, wajib port 5433, CA PG |
| `DPR_ADMIN_USER_PASSWORD` | Role DB coordinator, hanya fungsi maintenance wrapped PII |
| `DPR_SCANNER_USER_PASSWORD` | Akses baca terproteksi untuk validator |
| `DPR_ROTATION_BOOTSTRAP_USER`, `DPR_ROTATION_BOOTSTRAP_PASSWORD` | Khusus `prepare`, default username postgres |
| `DPR_SECRETS_DIR` | Khusus pilihan lokal DPAPI; folder eksternal yang sudah ada |

Isi password/token melalui pengelola rahasia; jangan literal di shell history,
argv, file repo atau chat. Tidak ada opsi CLI untuk password/token. Root token
dan unseal share tidak diterima oleh tool rotasi. Token policy dari tahap 1 yang
sudah kedaluwarsa perlu diterbitkan ulang oleh operator, lihat `infra/README.md`.

## Perintah PowerShell

Contoh menggunakan kredensial DB DPAPI lokal yang sudah tersedia. Token tetap dari
environment; `--local-credentials` tidak membaca root token atau unseal key.

```powershell
$env:DPR_SECRETS_DIR = Join-Path $env:LOCALAPPDATA 'DPR\crypto-infra-tls'
python -m infra.rotation --local-credentials prepare --database protected_734
python -m infra.rotation --local-credentials prepare --database protected_100k
python -m infra.rotation --local-credentials rotate --database protected_734 --database protected_100k
```

`rotate` melakukan **satu rotasi pii-kek untuk seluruh daftar database**, kemudian
batch rewrap 100 baris memakai target versi eksplisit. Hanya `dek_pii_wrapped`
diubah; trigger normal memperbarui updated_at dan mencatat audit. Tidak mengubah
field ciphertext, DEK, wrapped FIN, blind index, REF, atau protection_version.

Sertakan `--database protected_1m` jika sudah ada dan sudah di-prepare. Tidak ada
hardcode jumlah baris atau kewajiban dataset 1m untuk menjalankan 734/100k.
Database yang tidak ikut operasi masih terbaca dengan versi lama, karena tidak
ada versi key yang dinonaktifkan. Backup lama juga tidak otomatis direwrap.

Tanpa DPAPI, hilangkan `--local-credentials` dan sediakan seluruh env credential
di tabel. `--evidence-dir` sebelum subcommand memisahkan laporan tiap eksekusi.

## Hasil dan melanjutkan proses

`evidence/keys/rotation.json` berisi versi sebelum/tujuan/sesudah, jumlah wrapped
key tiap versi per DB, jumlah baris/batch, waktu, dan hasil verifikasi seluruh
record. Checkpoint ditulis atomik setelah batch commit. Tidak berisi wrapped DEK,
plaintext, digest plaintext/DEK, token, atau password.

Jika operasi berhenti sesudah key berotasi, gunakan **versi tujuan yang sama**:

```powershell
python -m infra.rotation --local-credentials rotate --database protected_734 --database protected_100k --resume-version 2
```

Ganti 2 dengan `target_version` pada laporan, bukan selalu angka 2. Resume tidak
memanggil rotate key lagi dan melewatkan baris yang sudah versi tujuan/lebih baru.
`--max-batches` dapat dipakai untuk demonstrasi pause/resume; status `paused` bukan
klaim migrasi seluruh wrapped key sudah selesai.

Jika koneksi terputus saat permintaan rotate dan laporan masih `rotate_requested`
atau versi tujuan belum diketahui, **jangan ulangi rotate secara buta**. Operator
memeriksa metadata key di OpenBao dan koordinasi perubahan yang terjadi, lalu
menentukan `--resume-version`. Tool sengaja tidak retry operasi rotate non-idempoten.

DB update memakai compare-and-swap wrapped key lama, dalam satu transaksi per
batch. Konflik menggagalkan batch tanpa menimpa perubahan aplikasi. Advisory lock
mencegah dua coordinator pada DB yang sama; tidak memblokir seluruh aplikasi atau
operator dari cluster lain. Perubahan bisnis bersamaan akan menggagalkan verifikasi
before/after; gunakan maintenance dan resume, bukan mengabaikan hasil gagal.

## Test

```powershell
python -m pytest infra/rotation/tests toolkit/tests/test_rotation_client.py -q
$env:DPR_ROTATION_INTEGRATION = '1'
python -m pytest infra/rotation/tests toolkit/tests/test_rotation_client.py -q
Remove-Item Env:DPR_ROTATION_INTEGRATION
```

Integration menggunakan 17 record sintetis buatan sendiri dan container TLS
sementara. Menguji rotasi v1→v2, pause/resume, repeat idempoten, ACL fungsi,
CAS/penolakan batch invalid, decrypt seluruh record dan restore backup sebelum
rotasi. Evidence: `evidence/keys/integration.json`.
