# Update tampilan layanan

Paket ini hanya source `app/web`: perbaikan filter analytics dan penyederhanaan
login/sidebar/header/profil sesuai screenshot pengguna. Tidak perlu menjalankan SQL A5, handoff,
provision akun, atau migrasi ulang. Backend tetap berjalan. Web berhenti sementara
selama build dan kemudian dijalankan lagi. Gunakan instalasi Node/dependency VM existing.

## PowerShell laptop, dari root repo juara1onno

```powershell
cd "C:\D thinkpad\zhafif tugas\Semester 7\hackathon-dpr\web_user\juara1onno"
Get-FileHash app/.local/dpr-analytics-ui.tar -Algorithm SHA256
scp -i "$env:USERPROFILE\.ssh\id_ardi" app/.local/dpr-analytics-ui.tar ubuntu@43.156.157.247:dpr-analytics-ui.tar
```

Manifest hash dan commit ada di `app/.local/analytics-ui-package.json`.

## Terminal Ubuntu yang menjalankan web (npm start, port 3443)

Tekan Ctrl+C sekali. Jangan menghentikan terminal backend Uvicorn port 8100.

```bash
cd ~/juara1onno
sha256sum ~/dpr-analytics-ui.tar
# Jika cocok dengan hash laptop:
tar -xf ~/dpr-analytics-ui.tar -C ~/juara1onno
export PATH="$HOME/dpr-demo-zhafif/runtime/node/bin:$PATH"
cd app/web
npm run build
```

Hanya setelah build berhasil:

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

Biarkan terminal tetap terbuka. Login analyst lalu hard refresh Ctrl+Shift+R pada
`https://43.156.157.247/analytics`. Tampil panel Filter statistik dengan padding,
Terapkan hijau dan Reset outline. Input bertumpuk pada layar kecil. Kartu total
tanpa nilai dan teks berulang dihapus; total API tetap null, label kecil tetap hilang.
Login menjadi kartu ringkas; panel promosi, kartu keamanan sidebar, indikator sesi,
dan catatan backend pada profil dihapus. Identitas akun dan tombol Keluar tetap ada.

Jika aplikasi belum memakai backend/SQL A5, panduan UI ini bukan pengganti rilis
[A5](DEPLOY_A5.md). Masalah token svc-app kedaluwarsa juga terpisah dari tampilan.
