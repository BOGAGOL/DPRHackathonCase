# 7. Panduan teknis penerapan, pemulihan dan sumber daya

Perintah di sini adalah bahan prosedur pada laporan, **bukan pekerjaan yang
dijalankan saat menulis konteks**. Operator memilih fresh/existing, memverifikasi
hak akses, environment dan maintenance. Tidak menjalankan semua contoh berurutan
pada database aktif. Password/token/key hanya dimuat dari storage privat/env.

## Prasyarat dan penanggung jawab

Python 3.11+, Git, virtualenv, Node/npm untuk frontend, PG 18 client/server,
OpenBao 2.5.5, CA/server cert SAN yang cocok, Docker/Compose V2 untuk jalur container,
Chrome untuk acceptance browser. Ubuntu fresh VM dan Windows lab berbeda cara
penyimpanan privat dan service manager. Hindari sudo Python/root runtime aplikasi.

DBA menyiapkan DB/role minimum; key custodian menyiapkan TLS/transit/token/recovery;
operator aplikasi menyiapkan origin/service/akun/scope; pemilik benchmark mengunci
target/data/run; reviewer memeriksa kelas data dan klaim. Jangan memberi login DB
dan root Bao ke satu service dengan alasan memudahkan setup.

## Urutan penerapan yang disarankan

| Fase | Pekerjaan dan kriteria keluar | Rollback/batas |
|---|---|---|
| 0 Inventaris | Pilih instance/environment, source immutable, kebutuhan layanan, baseline dan target, custody, ruang disk | Tidak merusak stack existing; jangan reinit/mengganti key |
| 1 Assessment | Scanner, review ground truth, priority/profile, akses dan kebutuhan pencarian | Review ulang override yang ambigu; belum migrasi |
| 2 Fondasi | CA/TLS verify, role, Transit/policy, token TTL, admin terpisah | Sertifikat/key salah diperbaiki sebelum data terenkripsi dibuat |
| 3 Migrasi | Target baru, snapshot, batch/checkpoint, full validation, revokasi sementara | Source tetap ada; resume job sama, jangan overwrite source |
| 4 Integrasi layanan | Akun/scope/marker B, URL role DB, A5 aggregate query, DTO/CSRF/header | Upgrade spesifik; tidak mengulang provisioning demo aktif |
| 5 Acceptance/cutover | Role×record×field, fail closed, JSON/storage, TLS, smoke | Kembali konfigurasi layanan lama bila diputuskan aman; jaga target untuk diagnosis |
| 6 Operasi | Backup/encrypted manifest, restore baru, audit, TTL/unseal/cert renewal, rotasi | Verifikasi sebelum membuka CONNECT/runtime |
| 7 Evaluasi | B/P sebanding, raw/median, residual, target dan hasil gagal | Tidak melonggarkan target sesudah hasil |

## Environment tanpa contoh secret aktif

Pisahkan DPR_SECRETS_DIR/DPR_PRIVATE_DIR/DPR_BACKUP_DIR di luar repo. Simpan CA
publik, key privat, credential role, init material dan tokens pada folder operasional
dengan izin minimum; jangan satu folder web static. DPAPI lokal Windows tidak
portable ke akun/laptop lain; VM memakai file permission dan custody operator.

Variabel penting: PGHOST/PGPORT/PGSSLROOTCERT; credential source/target terpisah;
OPENBAO_ADDR=https://host:8200, OPENBAO_CACERT, token policy; MODE dan role URL B;
DPR_BACKUP_KEY_B64 serta DPR_BACKUP_HMAC_KEY_B64 dua key 32 byte berbeda;
APP_ORIGIN dan service TLS/trust. Jangan mengisi laporan dengan connection URL
berpassword, token contoh menyerupai token asli atau output shell environment.

## Contoh reproduksi komponen

```powershell
# Jalur Python; install pin modul terpisah jika diperlukan.
python -m venv .venv
.venv/Scripts/python -m pip install -r infra/requirements.txt -r app/requirements.txt
.venv/Scripts/python -m pip install -e toolkit

# Status aman; init hanya untuk Bao benar-benar baru.
python -m infra.openbao.init status
# python -m infra.openbao.init init
# python -m infra.openbao.init unseal  # prompt tersembunyi, dua share berbeda
# python -m infra.openbao.init configure
# python -m infra.openbao.init issue --ttl-seconds 3600

# Target BARU dan credential privat sudah disiapkan.
python -m migration prepare --target protected_100k
python -m migration check --source baseline_100k --target protected_100k
python -m migration run --source baseline_100k --target protected_100k --profile policy/protection_profile.yaml
# 1M: pasangan baseline_1m / protected_1m; demo: postgres / protected_734.
```

Default run memvalidasi dan mencabut token migrasi sesudah sukses. NOLOGIN DB
ditutup sesuai runbook. Sesudah pause/fail, inspeksi checkpoint dan token; jangan
mengulangi prepare/init/rotasi tanpa memahami state. Fresh VM bootstrap mempunyai
helper infra.vm init-secrets dan Compose VM; database/container existing mempunyai
enable_tls inspect/apply/verify yang berbeda. TLS apply mengubah server, pull kode
saja tidak. Pengecualian baseline memakai alamat klien terkonfigurasi/auto,
bukan meng-hardcode 172.17.0.1 untuk semua Docker Desktop.

## Pengoperasian aplikasi pada VM yang sudah disiapkan

Kode deployment B menyediakan `app/scripts/run_runtime.sh api|web` dan dua unit
`dpr-api.service`/`dpr-web.service`. Launcher memakai environment bersih dan
memuat file app.env privat; cabang web menghapus variabel DB/OpenBao dari
environment sebelum menjalankan npm. Ini membatasi pewarisan secret lewat env,
bukan bukti bahwa proses dengan UID/akses filesystem yang sama mustahil membaca
file konfigurasi tersebut bila proses/OS sudah dikuasai.

Unit berjalan sebagai ubuntu, memakai restart-on-failure, UMask0077,
NoNewPrivileges, PrivateTmp, ProtectSystem=strict dan ProtectHome=read-only.
Beberapa path operator/key-plane dibuat tidak dapat diakses service; web mendapat
write path .next yang diperlukan. Konfigurasi ini adalah hardening yang tersedia
dalam source, bukan klaim seluruh opsi sudah diperiksa langsung pada setiap VM.

Installer `scripts/deploy/install_app_services.sh` dibatasi untuk user/path
deployment yang ditetapkan. Ia menolak port 8100/3443 yang masih dipakai atau unit
existing yang bukan miliknya, memvalidasi unit, mengaktifkan dua service dan
memeriksa readiness lewat HTTPS dengan CA. Tidak menghentikan layanan host lain.
Operator melakukan maintenance secara sadar; jangan menjalankan installer hanya
karena source baru di-pull. Golden reset/pentest kit mempunyai guard dan prosedur
berbeda, bukan rollback otomatis semua layanan/key-plane.

## Backup dan integritas

pg_dump -Fc sebagai backup_user mengalir ke AES-GCM terframe; tidak ada file dump
plaintext sementara. Format ini AES-GCM proyek, bukan age. Kunci backup berbeda
dari DEK/KEK domain; HMAC manifest memakai key berbeda lagi. Manifest memuat
artifact id, waktu, ciphertext SHA256, ukuran, row counts, retention deadline. HMAC
mengautentikasi metadata; hash tanpa key saja tidak mencegah penggantian manifest.

```powershell
python -m scripts.backup backup --source protected_100k
python -m scripts.backup restore --manifest "$env:DPR_BACKUP_MANIFEST"
python -m scripts.backup restore --manifest "$env:DPR_BACKUP_MANIFEST" --with-openbao
python -m scripts.backup tamper-test --manifest "$env:DPR_BACKUP_MANIFEST"
python -m scripts.backup retention-test --manifest "$env:DPR_BACKUP_MANIFEST"
```

DPR_BACKUP_MANIFEST pada contoh adalah variabel path operator, bukan secret pada
argv. Password/key tidak punya opsi CLI. init-keys/local-credentials adalah
kemudahan DPAPI Windows, bukan perintah di semua Linux. Retention test hanya clone
milik test dengan anggota buatan sendiri; jangan menghapus record panitia/benchmark.

Restore memverifikasi HMAC+SHA256 dan mengautentikasi seluruh frame **sebelum**
memulihkan DB. Agar tetap tanpa file plaintext, pemeriksaan dan pemulihan dapat
memerlukan pembacaan ciphertext kembali. Restore ke nama baru reserved
dpr_restore_<32hex>; tidak menimpa baseline/protected existing. pg_restore menerima
stream decrypt. Layout A lima tabel atau A+B tujuh tabel diterima secara lengkap, bukan set
arbitrary. Role global tidak berada dalam pg_dump; bootstrap role dengan password baru
pada cluster pengganti terpisah. ACL/RLS/A5/CONNECT/TLS diperiksa sebelum runtime.

Tanpa Bao: count/structural/ACL dapat lulus tetapi nilai tetap ciphertext. Dengan Bao:
smoke decrypt sampel sah. Aplikasi baru benar-benar “pulih” setelah DB selection,
marker, akun/sesi/scope, API/UI dan TLS juga diuji. Arsip lima tabel lama bukan backup
akun/sesi yang belum dibuat. Service restore dapat dipilih dengan
DPR_RESTORED_DATABASE yang cocok marker; jangan hanya mengganti URL ke DB arbitrer.

## Retensi, custody dan bencana

Default retention 30 hari dicatat manifest. Deletion test membuktikan record hilang
dari backup baru setelah delete pada clone; backup lama tetap memuatnya sampai
retensi berakhir. Tidak ada scheduler purge/secure erase SSD yang otomatis dibuktikan.
Tetapkan owner retensi, verifikasi expiry, legal hold bila relevan, catat penghapusan
arsip dan salinan. Crypto erasure hanya efektif jika seluruh salinan key/domain
yang relevan benar-benar tidak dapat dipulihkan; jangan mengklaim sudah dilakukan.

Kunci backup, key HMAC, storage Bao beserta KEK, shares/recovery, CA/cert dan password
role memerlukan backup/custody masing-masing. Membuat pii-kek dengan nama sama
di Bao baru tidak membuka wrapper dari Bao laptop lain. Fresh deploy bisa memilih
migrasi ulang dari source privat dengan key baru. Pemulihan full key-plane lintas
mesin memerlukan drill terpisah; unseal volume lama tidak membuktikannya.

Saat insiden: batasi akses, simpan metadata aman, revoke token, hentikan pemakaian
cache/clear, identifikasi domain/versi, putuskan rotasi/rewrap atau reenkripsi,
pulihkan ke target baru, validasi sebelum cutover. Rotasi pii-kek:

```powershell
python -m infra.rotation prepare --database protected_100k
python -m infra.rotation rotate --database protected_734 --database protected_100k
# Resume memakai --resume-version versi job yang sama; jangan rotate lagi membabi buta.
```

## Kebutuhan resource dan biaya

Snapshot storage laptop:100k baseline 104.732.351 byte/protected 230.012.607 byte;
1M baseline 825.194.175 byte/protected 2.210.617.023 byte (~2,679×). Ini snapshot
setelah tahap tertentu, bukan angka tetap setelah VACUUM/WAL/workload berubah.
Rencanakan source+target+WAL+index+backup+restore clone+Bao+raw benchmark, bukan hanya
dua kali ukuran tabel. Sediakan headroom disk dan budget token untuk validasi penuh.

Biaya yang perlu dihitung instansi: CPU/RAM dan latensi API/Bao, kapasitas disk,
backup off-host, TLS/renewal, operator/kustodian, monitoring, review/audit dan
waktu maintenance. Tidak ada angka rupiah/RPO/RTO produksi tervalidasi pada repo.
Jelaskan metode estimasi (beban nyata × resource ukur + safety factor + retensi), lalu
ukur ulang pada topologi/hardware instansi; jangan memindahkan benchmark laptop
menjadi SLA produksi.
