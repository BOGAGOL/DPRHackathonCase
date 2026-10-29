# Operasi dan pemulihan

Untuk demo lokal gunakan command pada [README](../README.md). Bagian ini untuk
operator instalasi permanen. Jangan menjalankan init/import/prepare/provision ulang
pada layanan existing hanya untuk update kode. Data sumber dan baseline tidak menjadi
target penulisan; restore/migrasi selalu membuat database baru yang diizinkan.

## Instalasi permanen baru — Linux

Prasyarat Python3.11+, Docker/ComposeV2, Node/npm dan user non-root. Port loopback5433
serta8200 harus tersedia. Periksa container/volume project dpr-demo terlebih dahulu;
jika sudah ada, gunakan prosedur operasional existing, bukan mengulang bootstrap.

Letakkan SQL sumber privat di ~/dpr-runtime/private/input/02_data.sql sebelum tahap
import. Perintah unseal meminta dua share berbeda melalui prompt tersembunyi; jangan
menulis share dalam command. Init dilakukan sekali. Bootstrap menerbitkan token
workload maksimum4jam. Pisahkan root/shares ke kustodian/recovery storage sesudah init.

```bash
cd ~/juara1onno
python3 --version
docker version
docker compose version
docker ps -a --filter label=com.docker.compose.project=dpr-demo
docker volume ls --filter label=com.docker.compose.project=dpr-demo

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r infra/requirements.txt
python -m pip install -e toolkit
umask 077
set +x
export DPR_SECRETS_DIR="$HOME/dpr-runtime/private/module-a"
export DPR_VM_PROJECT=dpr-demo

python -m infra.vm init-secrets
# compose.env hanya path/nama project/UID/GID, tanpa password atau token.
set -a
. "$DPR_SECRETS_DIR/compose.env"
set +a
export OPENBAO_ADDR=https://127.0.0.1:8200
export OPENBAO_CACERT="$DPR_SECRETS_DIR/tls/ca.crt"

python -m infra.tls.make_ca
python -m infra.postgres.make_cert

a_compose() {
  docker compose -p "$DPR_VM_PROJECT" -f infra/vm/compose.yaml "$@"
}
a_compose up -d
a_compose ps
a_compose exec -T postgres pg_isready -U postgres -d postgres

python -m infra.openbao.init status
python -m infra.openbao.init init
python -m infra.openbao.init unseal
python -m infra.openbao.init unseal
python -m infra.vm bootstrap-bao --ttl-seconds 14400

a_admin() {
  env -i HOME="$HOME" PATH="$PATH" DPR_SECRETS_DIR="$DPR_SECRETS_DIR" \
    bash --noprofile --norc -c \
    'set -a; . "$DPR_SECRETS_DIR/operator.env"; set +a; exec "$@"' _ "$@"
}
a_migration() {
  env -i HOME="$HOME" PATH="$PATH" DPR_SECRETS_DIR="$DPR_SECRETS_DIR" \
    bash --noprofile --norc -c \
    'set -a; . "$DPR_SECRETS_DIR/migration.env"; set +a; exec "$@"' _ "$@"
}

a_admin python -m infra.postgres.enable_tls apply
a_admin python -m migration prepare --target protected_734
a_admin python -m infra.postgres.enable_tls verify

install -d -m 0700 "$HOME/dpr-runtime/private/input"
chmod 0600 "$HOME/dpr-runtime/private/input/02_data.sql"
python -m infra.vm import-source \
  --source "$HOME/dpr-runtime/private/input/02_data.sql"
python -m infra.vm workload-env

a_migration python -m migration check --source postgres --target protected_734
a_migration python -m migration run --source postgres --target protected_734 \
  --profile policy/protection_profile.yaml --expected-rows 734 --batch-size 100
python -m infra.vm retire-migration
python -m infra.vm verify

python -m infra.vm handoff --app-origin https://SUBDOMAIN-YANG-DISETUJUI

env -i HOME="$HOME" PATH="$PATH" DPR_SECRETS_DIR="$DPR_SECRETS_DIR" \
  bash --noprofile --norc -c '
    set -a
    . "$DPR_SECRETS_DIR/handoff/app.env"
    . "$DPR_SECRETS_DIR/handoff/setup.env"
    set +a
    python app/scripts/schema.py --database protected_734 &&
    python app/scripts/provision.py
  '
```

Ubah origin placeholder menjadi HTTPS origin yang dipakai. Handoff menyimpan env
runtime dan setup secara terpisah di folder privat. Setup/admin env tidak boleh
masuk proses API atau frontend. Material Windows DPAPI tidak menjadi escrow Linux.

## Startup aplikasi

Instal requirements layanan + toolkit, lalu npm ci dan npm run build pada app/web.
Muat hanya handoff/app.env ke proses API. Jalankan `python app/scripts/serve.py`.
Frontend dijalankan `npm start` pada app/web dengan cert/key, API_INTERNAL_URL HTTPS,
NODE_EXTRA_CA_CERTS, APP_ORIGIN dan WEB_PORT. Reverse proxy/domain sertifikat publik
mengarah ke listener lokal; jangan membuka port PostgreSQL/OpenBao ke Internet.
Launcher menolak HTTP dan TLS tanpa material lengkap.

Untuk memperbarui token svc-app, operator menggunakan `python -m infra.vm refresh-app`
dengan custody bootstrap yang sah. Restart hanya service yang memerlukan env token
baru. API tidak mengambil root token secara otomatis. Untuk instalasi systemd,
[refresh token opsional](TOKEN_REFRESH.md) memakai broker AppRole terpisah yang
menerbitkan token svc-app berbatas TTL lalu merestart API. Fitur perlu dipasang
operator; pull kode tidak mengaktifkannya. Unseal tetap manual.

## Backup dan restore

Gunakan `python -m scripts.backup --help` untuk subcommand backup/restore/tamper-test/
retention-test. Credential backup_user, admin restore, CA, kunci enkripsi backup dan
HMAC diberikan melalui environment/penyimpanan privat; tidak melalui argumen shell.
Backup pg_dump-Fc di-stream langsung ke enkripsi, tanpa file dump plaintext sementara.
Manifest mencatat hash artefak terenkripsi, row count, ukuran, waktu dan retensi.

Restore memverifikasi HMAC, SHA256 dan semua frame AEAD sebelum membuat DB baru.
Tanpa akses OpenBao data tetap ciphertext; dengan akses kunci dilakukan smoke decrypt.
Nama restore dpr_restore_<random> dan marker/OID diperiksa sebelum cleanup/cutover.
Simpan key plane dan kunci backup terpisah; database protected saja tidak cukup
untuk recovery layanan dengan key plane baru yang memiliki nama key sama.

Sebelum cutover, periksa seluruh tabel kontrol aplikasi, role, ownership, RLS,
view analis, sequence, jumlah baris dan akses enam akun. Ganti env runtime melalui
DPR_RESTORED_DATABASE hanya setelah verifikasi lulus. Pertahankan target lama untuk
rollback dan jangan mencampur session/control table antardatabase.

## Rotasi dan perubahan ACL

`python -m infra.rotation --help` menampilkan prosedur rotate/rewrap pii-kek. Rotasi
mengubah versi KEK/wrapped DEK, bukan isi field AEAD. Key-operator terpisah dari DB;
jangan menaikkan minimum decryption version sebelum wrapper dan recovery diverifikasi.

ACL analis: `python -m infra.protected.analyst --help`; terapkan aggregate-only lalu
verifikasi dengan analyst_user. Unique index identitas tersedia di
sql/protected/04_identity_unique.sql; skrip menolak duplikat existing, bukan menghapus
record otomatis. Koordinasikan maintenance analytics/identity dengan rilis aplikasi.

## Retensi dan penghentian

Demo sementara dihentikan Ctrl+C; hanya proses/project milik run yang dihentikan.
Folder privat native di temporary-directory/dpr-reproduction/<run-id> dapat berisi
cluster sumber, recovery material dan arsip terenkripsi. Hapus secara terarah setelah
tidak lagi dibutuhkan; tidak ada prune Docker global atau klaim secure erase media.

Untuk produksi tetapkan retensi, jadwal purge, backup key plane/custody, RPO/RTO,
pemantauan TTL/sertifikat dan kebutuhan HA. Record terhapus pada backup baru tidak
menghilangkan salinannya dari backup lama sampai kebijakan retensi diterapkan.

## Login browser ditolak HTTP403

Pemeriksaan terbaru pada URL publik: GET login200/TLSvalid, CSRF cookie tersedia,
POST login dengan Origin URL publik403, sedangkan diagnostik non-browser tanpa
Origin dengan akun yang sama200 dan identitas cocok. Ini indikasi origin runtime
belum sesuai, bukan alasan mengganti password atau menonaktifkan kontrol.

Operator VM perlu:

1. Periksa origin yang dipakai pengguna (scheme, host dan port persis).
2. Samakan APP_ORIGIN pada environment backend dan frontend/reverse proxy dengan
   origin tersebut. Untuk URL IP yang disediakan: https://43.156.157.247 tanpa trailing slash.
3. Restart layanan terkait memakai process/service manager yang sudah terpasang.
   Mengubah env di laptop atau pull kode saja tidak mengubah environment proses VM.
4. Ulangi login enam akun melalui browser, lalu periksa record/field/analytics/audit
   sesuai peran. Jangan mengklaim lulus berdasarkan GET halaman login saja.

Tidak ada perubahan konfigurasi VM pada pemeriksaan ini. Bukti diagnostik di
`evidence/acceptance/deployed-origin-diagnosis.json`. Akses anggota tetap read-only;
login/logout hanya menghasilkan metadata sesi/audit normal.

## Interface CLI backup mandiri

Variabel koneksi: PGHOST, PGPORT, PGSSLROOTCERT, DPR_BACKUP_PASSWORD (backup_user),
DPR_RESTORE_USER dan DPR_RESTORE_PASSWORD (operator restore). Kunci terpisah:
DPR_BACKUP_KEY_B64 dan DPR_BACKUP_HMAC_KEY_B64, masing-masing base64 dari32byte acak.
Store: DPR_BACKUP_DIR, folder privat di luar repo. Akses decrypt opsional memakai
OPENBAO_ADDR, OPENBAO_CACERT dan OPENBAO_VALIDATION_TOKEN dengan policy svc-app.
Sediakan nilai melalui secret injection; tidak dicantumkan literal dalam command.

Setelah variabel privat tersedia, gunakan direktori evidence baru agar hasil lama
utuh. Berikut urutan perintah; ganti path manifest dengan output backup tersebut:

```powershell
python -m scripts.backup --container pg-dpr --evidence-dir evidence/backup-session backup --source protected_734
python -m scripts.backup --container pg-dpr --evidence-dir evidence/restore-session restore --manifest "C:/private/archives/ARTIFACT.manifest.json"
python -m scripts.backup --container pg-dpr --evidence-dir evidence/restore-key-session restore --manifest "C:/private/archives/ARTIFACT.manifest.json" --with-openbao
python -m scripts.backup --container pg-dpr --evidence-dir evidence/tamper-session tamper-test --manifest "C:/private/archives/ARTIFACT.manifest.json"
```

Nama container dan path di atas adalah pilihan operator, bukan target otomatis.
Jangan menjalankannya pada instance lain tanpa otorisasi. Di Linux gunakan path
Linux. Alur734 pada launcher melakukan operasi setara secara otomatis di stack baru.
