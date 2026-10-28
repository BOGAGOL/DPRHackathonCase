# Paket Modul A untuk VM Ubuntu baru

Untuk Zhafif: jalankan dari `~/juara1onno` pada VM baru, sebagai user biasa yang
diizinkan memakai Docker. Paket ini menyiapkan PostgreSQL 18, OpenBao **2.5.5**, TLS,
role/RLS, dan `protected_734`. Pemasangan web, routing domain, service manager dan
enam akun aplikasi tetap dikerjakan Modul B. Tidak memerlukan akses SSH Alby.

**Pilih jalur fresh:** buat key plane baru dan migrasikan ulang 734 record di VM.
Dump protected dari laptop tidak bisa dibuka oleh OpenBao baru hanya dengan membuat
nama kunci yang sama. Tidak menyalin root token/shares/kunci laptop ke Git atau chat.

## 0. Prasyarat dan batas instalasi

- Python **3.11+**, modul venv, Docker Engine rootful dan Compose V2 sudah tersedia.
  Ubuntu 24.04 umumnya memakai Python 3.12; periksa versi sebenarnya.
- Akses repo PRIVATE tim. Kode paket ini harus tersedia pada checkout yang dipakai.
- Port loopback **5433** dan **8200** tersedia. Jika sudah dipakai, koordinasikan;
  jangan mengubah PostgreSQL/OpenBao layanan lain. Paket tidak memakai port 5434.
- Ini prosedur **VM/stack baru**. Bila sudah ada container/volume project `dpr-demo`,
  berhenti pada inventaris dan minta validasi; jangan menjalankan inisialisasi ulang.
- Dataset panitia `02_data.sql` disediakan lewat penyimpanan privat. Contoh path:
  `~/dpr-demo-zhafif/private/input/02_data.sql`. Tidak disajikan oleh web.

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
export DPR_SECRETS_DIR="$HOME/dpr-demo-zhafif/private/module-a"
export DPR_VM_PROJECT=dpr-demo
```

Jalankan sebagai operator `ubuntu`, bukan `sudo python`: UID/GID operator dipakai
container OpenBao agar file TLS mode 0600 dapat dibaca tanpa dibuat world-readable.
Direktori Modul A tersendiri; helper tidak mengubah permission home atau folder tim.

## 1. Material privat, CA, dan container

```bash
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
```

Tunggu PostgreSQL healthy. OpenBao masih sealed/uninitialized pada start pertama,
sehingga belum healthy; ini bukan alasan mematikan TLS. PostgreSQL memakai named
volume pada `/var/lib/postgresql`, sesuai layout PG18. Password bootstrap dibaca
dari file privat, bukan literal argumen/environment container. CA signing key dan
bootstrap material OpenBao tidak dipasang ke container.

Service `bao-volume` hanya mengatur owner/mode root direktori volume OpenBao milik
project ini. OpenBao berjalan dengan UID/GID operator, `SKIP_CHOWN=1`, dan membaca
file TLS read-only. Root job itu tidak diberi network atau mount direktori host.

## 2. Init dan unseal OpenBao secara manual

```bash
python -m infra.openbao.init status
python -m infra.openbao.init init
python -m infra.openbao.init unseal
python -m infra.openbao.init unseal
python -m infra.vm bootstrap-bao --ttl-seconds 14400
```

Kedua pemanggilan `unseal` harus dijalankan pada terminal SSH interaktif. Masukkan
share berbeda lewat prompt tersembunyi, bukan argumen shell. `init` hanya sekali.
Material awal ada di `$DPR_SECRETS_DIR/openbao/init-material.json` mode 0600.
**Material lab awal berisi root dan tiga shares bersama:** pindahkan shares ke
kustodian terpisah dan root ke penyimpanan pemulihan privat sesuai runbook.
Jangan mengirim isi file melalui chat/log/screenshot. Operator bootstrap dapat
mengakses material ini; runtime aplikasi tidak menerima root atau shares.

`bootstrap-bao` mengaktifkan Transit, membuat `pii-kek`, `finance-kek`, `search-hmac`
dan empat policy kontrak, lalu menerbitkan token orphan TTL maksimum empat jam.
Ia tidak melakukan unseal atau rotasi kunci existing. Token disimpan di private
directory. Bila sealed, operasi gagal sampai operator melakukan unseal manual.

## 3. TLS PostgreSQL dan schema/role protected

Buat dua fungsi berikut. Masing-masing menjalankan child dengan environment bersih;
password/token hanya dimuat dari file privat yang sesuai. Jangan mengaktifkan `set -x`.

```bash
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
```

TLS updater hanya reload, bukan recreate/restart container. Semua protected dan
nama restore diwajibkan TLS; tidak ada pengecualian plaintext baseline pada VM demo
ini. Laporan TLS dapat mencatat baseline/target lain belum dibuat; yang wajib untuk
paket ini adalah `protected_verify_full:protected_734` dan penolakan non-TLS.

`prepare` adalah fase awal sebelum pemasangan kontrol B. Jangan mengulang prepare
setelah akun/tabel B aktif: provisioning A mengatur ulang grant kontraknya. Gunakan
`infra.vm verify` untuk pemeriksaan setelah migrasi, bukan prepare ulang.

## 4. Initial import source pada instance baru, lalu migrasi 734

Sediakan file lewat jalur privat terlebih dahulu dan batasi permission lokasi input:

```bash
install -d -m 0700 "$HOME/dpr-demo-zhafif/private/input"
chmod 0600 "$HOME/dpr-demo-zhafif/private/input/02_data.sql"
python -m infra.vm import-source \
  --source "$HOME/dpr-demo-zhafif/private/input/02_data.sql"
python -m infra.vm workload-env

a_migration python -m migration check --source postgres --target protected_734
a_migration python -m migration run --source postgres --target protected_734 \
  --profile policy/protection_profile.yaml --expected-rows 734 --batch-size 100
python -m infra.vm retire-migration
python -m infra.vm verify
```

Importer hanya bekerja pada container berlabel `dpr.scope=vm-demo`, membandingkan
system identifier koneksi TLS dengan container, dan menolak source table existing.
Ia mem-parsing INSERT literal, tidak mengeksekusi dump secara bebas, serta membuang
DROP dari schema baseline sebelum CREATE. Initial import harus menghasilkan
734 baris, NIK unik 734/panjang 14, dan 367 status menikah/tanggal pernikahan.
Setelah initial import ini, `postgres.public.anggota` hanya dibaca, tidak ditimpa.

Migrasi memakai scanner_user SELECT-only untuk source dan migration_user untuk
target, dengan token svc-migration dan validator svc-app yang terpisah dari root.
Semua field seluruh 734 baris diperiksa di memori. Run sukses mencabut token migrasi;
`retire-migration` memeriksa job validated/count sebelum menjadikan role NOLOGIN.
Verifier mengulang decrypt-and-compare seluruh 734 record melalui koneksi read-only,
memeriksa TLS/role/FORCE RLS, default deny app, deny analyst/auditor pada tabel dasar,
backup tanpa UPDATE, dan penolakan identitas migrasi. Tidak mencetak nilai anggota.

Jika proses terputus saat job belum selesai, pertahankan DB/volume/kunci dan ikuti
resume migration/README.md memakai identitas yang masih sah. Setelah complete,
jangan menjalankan ulang init/import/prepare untuk "memperbaiki" layanan.

## 5. Handoff privat ke Modul B

Isi origin publik yang sudah disepakati dengan pemilik routing. `localhost` dapat
dipakai untuk probe internal, tetapi harus diganti sebelum web dipublikasikan.

```bash
python -m infra.vm handoff --app-origin https://SUBDOMAIN-YANG-DISETUJUI
```

File privat yang dihasilkan:

URL loopback/path file pada handoff ini ditujukan untuk proses B yang berjalan
langsung pada host VM (misalnya systemd). Jika B dikemas dalam container bridge,
alamat loopback/path host tidak berlaku di dalam container; koordinasikan network,
mount material runtime minimum dan hostname/SAN yang benar, tanpa mematikan TLS.

| File di `$DPR_SECRETS_DIR/handoff/` | Pemakaian |
| --- | --- |
| `app.env` | Runtime B: URL app/analyst/auditor ke protected_734, CA, token svc-app, HTTPS leaf, APP_ORIGIN. Tanpa admin/root. |
| `setup.env` | Hanya trusted setup B: URL admin, contoh assignment 1/2 dan principal anggota demo, DPR_PRIVATE_DIR. Tidak dimuat service runtime. |

Contoh setup B dalam child terpisah, tanpa mengubah source B:

```bash
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

Zhafif menyesuaikan assignment bila diperlukan dan mengatur service/web/routing.
Provision B menolak akun existing. Akun demo/password yang dihasilkannya tetap di
private directory, bukan output chat. Runtime hanya memuat `app.env`, tidak `setup.env`
atau `operator.env`. Jangan menonaktifkan TLS verify untuk mengatasi error CA/hostname.
Leaf bawaan hanya untuk upstream lokal (localhost/127.0.0.1); HTTPS domain publik
memerlukan sertifikat domain yang sesuai pada routing B. Jika service memakai user
OS berbeda dari operator, berikan hanya environment runtime, CA publik dan leaf
TLS yang dibutuhkan melalui private directory milik service, lalu ubah path-nya;
jangan memberi akses folder bootstrap/operator sebagai jalan pintas.

## 6. Validasi yang dikirim kembali ke Alby

Selesaikan acceptance A sebelum demo mengubah field/menambah anggota; perbandingan
ke source asli memang akan menolak perubahan bisnis yang sudah sah setelahnya.
Kirim **hanya** ringkasan berikut melalui jalur evidence tim, tanpa material privat:

- `evidence/deployment/vm-verify.json` (passed, rows_compared 734, semua checks true).
- `evidence/migration/validation-protected_734.json` dan `revocation.json`.
- `evidence/infra/postgres-tls.json`, terutama protected_734 dan penolakan non-TLS.
- Hasil enam akun/web B dilaporkan oleh B setelah setup/HTTPS aktif.

Alby menilai bukti tersebut; hasil uji container lokal tidak dianggap hasil VM ini.
Source 734 dan input SQL masih plaintext dalam lingkungan privat untuk validasi;
paket ini tidak mengklaim seluruh filesystem VM aman bila semua salinan/source ikut bocor.

## Restart, token kedaluwarsa dan backup

- Setelah restart, start stack yang sama dan unseal manual dua kali. Tidak init ulang.
- Token svc-app maksimum empat jam, bukan identitas permanen. Sebelum expiry/demo,
  operator dengan akses bootstrap privat dapat menjalankan `infra.vm refresh-app`
  dan `infra.vm handoff` lagi, lalu B memuat ulang runtime environment. Refresh hanya
  menerbitkan svc-app, tidak menghidupkan kembali svc-migration/role migrasi.
  Token lama tetap berbatas TTL sampai kedaluwarsa atau dicabut operator terpisah.
- Pertahankan PostgreSQL/OpenBao volume, CA/kunci TLS, material recovery, dan private
  credentials melalui penyimpanan privat. OpenBao storage dan material pemulihan
  tidak disertakan Git. Kehilangan key plane dapat membuat wrapped DEK tidak terbuka.
- Setelah B menambah kontrolnya, gunakan backup tujuh tabel dan [runbook recovery](../../app/docs/RECOVERY.md).
  `stop` mempertahankan data; jangan memakai `down -v` pada instalasi VM yang dipakai.

Windows/PowerShell untuk membaca/mengetes paket tetap didukung melalui
`python -m infra.vm --help` dan `python -m pytest infra/vm/tests -q`.
File env yang dihasilkan adalah format Bash; credential XML DPAPI Windows tidak
dipindahkan ke Ubuntu. Penilaian risiko/klaim benchmark tetap mengikuti kontrak tim.
