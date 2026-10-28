# Rilis analytics A5/B4 ke VM Zhafif

Target hanya VM demo Ubuntu dan `protected_734`. Database/akun/assignment existing
dipertahankan. Jangan menerapkan perubahan pada laptop `pg-dpr` atau database
benchmark Delf sebelum benchmark selesai dan waktunya disepakati. Panduan SQL
kanonis: [Modul A](../../infra/protected/ANALYST_SUPPRESSION.md).

Checkout laptop sudah memuat PR A #10 (`822a199`), perubahan B ada pada branch
`feat/service-app`. Paket `.local` tidak masuk Git. VM dipasang melalui arsip, jadi
pull di laptop tidak memperbarui file atau database VM. Jangan mencoba `git pull`
di folder VM yang tidak mempunyai `.git`.

## 1. Unggah dari PowerShell laptop

Dari root repo `juara1onno`, gunakan paket yang disiapkan Codex dan periksa SHA256
di `app/.local/analytics-a5-package.json` sebelum/selesai transfer:

```powershell
Get-FileHash app/.local/dpr-analytics-a5.tar -Algorithm SHA256
scp -i "$env:USERPROFILE\.ssh\id_ardi" app/.local/dpr-analytics-a5.tar ubuntu@43.156.157.247:dpr-analytics-a5.tar
```

Paket hanya source terpilih B dan dependensi A yang sudah direview. Tidak memuat
dataset plaintext, credential, key, node_modules, virtualenv, atau build .next.
Parser source yang dibutuhkan helper A disertakan, tanpa CLI scanner/datagen.
Source backup A juga diperbarui agar memakai SQL A5 saat restore berikutnya.

## 2. Maintenance dan pembaruan kode

Untuk instalasi foreground yang dipakai saat ini: Ctrl+C di terminal web (`npm start`)
dan backend (`Uvicorn ...8100`). Nginx tetap hidup; aplikasi sementara tidak tersedia.
Jangan mematikan PostgreSQL/OpenBao atau menghapus volume. Ini maintenance terencana,
bukan rollback ke interface analis per record.

Di terminal SSH konfigurasi:

```bash
cd ~/juara1onno
sha256sum ~/dpr-analytics-a5.tar
# Hanya jika hash cocok dengan manifest laptop:
tar -xf ~/dpr-analytics-a5.tar -C ~/juara1onno
export PATH="$HOME/dpr-demo-zhafif/runtime/node/bin:$PATH"
cd app/web
npm run build
cd ~/juara1onno
```

Tidak ada perubahan dependency; gunakan node_modules/venv existing yang sudah
berhasil di VM. Jika build gagal, hentikan rilis dan kirim error tanpa rahasia.
Jangan menerapkan SQL saat build belum berhasil.

## 3. Terapkan SQL A5 dan verifikasi (satu per satu)

Environment administrator hanya dimuat dalam child untuk upgrade, tidak diwariskan
ke proses aplikasi. Operator tetap `ubuntu`; tidak memakai sudo python.

```bash
export DPR_SECRETS_DIR="$HOME/dpr-demo-zhafif/private/module-a"
a5_admin() {
  env -i HOME="$HOME" PATH="$PATH" DPR_SECRETS_DIR="$DPR_SECRETS_DIR" \
    bash --noprofile --norc -c \
    'set -a; . "$DPR_SECRETS_DIR/operator.env"; set +a; exec "$@"' _ "$@"
}
a5_admin /home/ubuntu/juara1onno/app/.venv/bin/python -m infra.protected.analyst \
  --database protected_734 --evidence app/evidence/access-control/vm-a5-apply.json
```

Hanya bila `passed: true`, lanjut:

```bash
a5_admin /home/ubuntu/juara1onno/app/.venv/bin/python -m infra.protected.analyst \
  --database protected_734 --verify-only \
  --evidence app/evidence/access-control/vm-a5-verify.json
```

Keduanya harus `passed: true`. CLI A memakai TLS verify-full dan transaksi dengan
timeout; tidak mengubah password, LOGIN, anggota, akun, sesi, assignment, atau sequence.
Jangan menjalankan migration prepare, full infra.protected.apply, datagen, init/unseal
ulang, atau provision akun untuk A5. OpenBao tidak dibutuhkan untuk upgrade ACL ini.

## 4. Jalankan aplikasi dengan environment runtime saja

Di terminal backend:

```bash
cd ~/juara1onno
env -i HOME="$HOME" PATH="$PATH" \
  DPR_SECRETS_DIR="$HOME/dpr-demo-zhafif/private/module-a" \
  bash --noprofile --norc -c '
    set -a
    . "$DPR_SECRETS_DIR/handoff/app.env"
    set +a
    exec /home/ubuntu/juara1onno/app/.venv/bin/python /home/ubuntu/juara1onno/app/scripts/serve.py
  '
```

Di terminal web terpisah:

```bash
env -i HOME="$HOME" PATH="$HOME/dpr-demo-zhafif/runtime/node/bin:$PATH" \
  DPR_SECRETS_DIR="$HOME/dpr-demo-zhafif/private/module-a" \
  bash --noprofile --norc -c '
    set -a
    . "$DPR_SECRETS_DIR/handoff/app.env"
    set +a
    cd /home/ubuntu/juara1onno/app/web
    exec npm start
  '
```

APP_ORIGIN existing harus tetap `https://43.156.157.247`. Tidak perlu handoff ulang
jika origin/token belum berubah. Jika svc-app sudah kedaluwarsa, ikuti refresh-app
Modul A dengan OPENBAO_ADDR/OPENBAO_CACERT yang benar, handoff origin yang sama,
kemudian restart runtime. A5 tidak mengganti TTL token maksimal empat jam.

## 5. Acceptance VM dan evidence

- `https://43.156.157.247/api/health/ready` tetap ready, login berfungsi.
- Login `analyst.demo`: analytics hanya kelompok yang jumlahnya >=5; label kelompok
  1–4 tidak muncul dalam JSON mentah. `total` null. Data anggota/detail tetap 403.
- Filter UI hanya dimension/value. Filter lama `?nama_kppn=...` atau kombinasi dengan
  pekerjaan_terakhir menghasilkan 422 eksplisit, tanpa nilai input pada error.
- Tiga staf masih mengikuti masking/per-field dan assignment sebelumnya (2 atau 734
  sesuai perubahan assignment yang benar-benar sudah diterapkan). Anggota tetap
  hanya pemilik; auditor hanya audit. Jangan memperluas izin sebagai cara memperbaiki
  analytics. Jumlah dan label NULL dengan count >=5 dapat tampil sebagai Tidak tersedia.
- Respons API: Cache-Control no-store. Browser tidak menyimpan token/data di storage.
- Verifikasi pembaruan sertifikat tetap aktif: `sudo /snap/bin/certbot renew --dry-run`.

Kirim `vm-a5-apply.json`, `vm-a5-verify.json` dan hasil acceptance B yang sudah
dijalankan, tanpa password, token, root/unseal material, atau salinan respons anggota.
Evidence unit/UI lokal bukan bukti SQL A5 sudah terpasang pada VM. Status VM A5
tetap NOT TESTED sampai hasil server aktual diterima. Setup systemd untuk proses
yang tidak bergantung pada terminal SSH masih pekerjaan deployment terpisah.

Jika upgrade SQL gagal, transaksi dibatalkan. Jika aplikasi baru gagal setelah SQL
berhasil, pertahankan maintenance; jangan mengembalikan grant analyst_view atau
menjalankan aplikasi lama untuk melewati ACL. Perbaiki rilis query A5.
