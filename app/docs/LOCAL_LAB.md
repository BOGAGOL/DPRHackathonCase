# Lab Zhafif: PostgreSQL 18 + TLS + baseline 100k

Jalankan dari root repo pada branch `feat/service-app`. Semua kode tambahan berada di `app/`.
Docker Desktop harus aktif. Instal dependensi `app/requirements.txt` dan `infra/requirements.txt`
ke venv yang sama; instal/build `app/web` dan Chromium sesuai README sebelum `verify`.
Datagen C diimpor dari checkout tanpa diubah. PostgreSQL bind hanya `127.0.0.1:5433`.

```powershell
# Gunakan app/.venv/Scripts/python bila memakai venv app dari README.
.venv/Scripts/python app/scripts/local_lab.py setup --dataset-ref cf2d2ccd786066ad9ea3c56ec2999987feda73ac
.venv/Scripts/python app/scripts/local_lab.py verify
.venv/Scripts/python app/scripts/check_ready.py
```

`setup` mengambil `sql/baseline/02_data.sql` dari Git commit tim tersebut langsung ke memori.
Tidak perlu menyalin dataset ke fixture atau evidence. Setup membuat container `pg-dpr` baru,
volume `dpr-zhafif-local_lab-data`, CA/server cert dari generator Modul A, password acak dan
akun enam peran. Nama container/label volume yang sudah ada milik pihak lain ditolak.
Jika instance tim sudah ada, skrip ini tidak mengadopsi, menghapus, merotasi password atau
mengonfigurasikannya; gunakan runbook pemilik instance tersebut.

Bootstrap pertama mengimpor 734 baris ke `postgres` yang masih kosong. Setelah bootstrap,
database sumber hanya dibaca; menjalankan ulang setup tidak mengimpor ulang. Datagen asli C
menghasilkan 100.000 baris seed 42 dan memvalidasi 29 field sumber + PK lokal. Target yang sudah
ada hanya divalidasi terhadap checksum tersimpan, tidak dibuat ulang. Hanya tujuan penulisan
report generator diarahkan ke `app/evidence/access-control/local-dataset.json`; implementasi
generator/validasi tetap milik C. Tidak ada berkas modul A/C yang diubah.

Folder privat default: `$env:LOCALAPPDATA\DPR\zhafif-local`. Untuk lokasi lain, set
`DPR_B_LAB_DIR` ke direktori khusus di luar checkout **sebelum setup**, lalu gunakan nilai sama
pada terminal berikutnya. ACL dibatasi dengan utility Modul A. File `state.json` memuat kredensial
database; `service-b/service-b-plain-accounts.json` memuat enam akun demo. Baca lokal bila perlu
login; jangan cetak/unggah isinya ke chat, terminal log, Git atau evidence.

Container hanya memasang subfolder runtime (server cert/key, CA publik dan password-file bootstrap).
CA signing key berada di `custody/`, tidak dipasang ke PostgreSQL. Sertifikat server berlaku 30 hari;
renewal perlu prosedur eksplisit, setup tidak menimpa kunci/sertifikat. Simpan direktori privat
beserta volume bila ingin memakai lab lagi; jangan jalankan `down --volumes` untuk penggunaan normal.

## Jalankan aplikasi untuk demo

Terminal backend:

```powershell
.venv/Scripts/python app/scripts/local_lab.py backend
```

Terminal frontend:

```powershell
.venv/Scripts/python app/scripts/local_lab.py web
```

Buka `https://localhost:3443/login`. Backend berada di `https://127.0.0.1:8100`.
Launcher mengisi environment runtime sendiri dari file privat; service hanya memperoleh
`app_user`, `analyst_user`, `auditor_user`, tanpa password postgres/bench/scanner atau token OpenBao.
Untuk browser interaktif, percayai CA lab pada perangkat sendiri melalui pengaturan sertifikat;
CA publiknya ada di `runtime/tls/ca.crt`. Skrip tidak memasang root CA otomatis ke trust store Windows.
Probe browser otomatis memakai pin sertifikat khusus lab. Tidak ada bypass TLS global.
Ctrl+C menghentikan proses aplikasi terminal tersebut. Container PostgreSQL tetap hidup untuk
benchmark; `docker stop pg-dpr` dapat dipakai saat lab selesai, `setup` menyalakan lagi dengan volume sama.

## Cakupan verifikasi

`verify` memeriksa validasi C + checksum sebelum uji, PostgreSQL 18, TLS semua role, penolakan
non-TLS dan CA salah, least privilege, RLS deny-default lokal, enam akun, DTO JSON persis,
kesesuaian field yang diizinkan dengan database, lookup KTP/email, halaman ke-2000,
IDOR, PATCH, insert, analytics dan audit. Selanjutnya browser Chromium memakai Next HTTPS →
FastAPI HTTPS → PostgreSQL verify-full, memeriksa CSP, cookie, storage dan alur enam peran.

Jalankan tanpa benchmark atau penulis lain yang aktif. File lock menolak verify bersamaan.
Skrip mengembalikan kontak yang berubah, menghapus hanya satu insert milik run itu dengan
ID/principal/KTP yang cocok, dan mengembalikan sequence jika tidak ada indikasi penulis lain.
Checksum seluruh baseline dan sumber diperiksa kembali, bukan sekadar jumlah baris.
Audit metadata uji tetap tersimpan; snapshot/reset antar benchmark resmi tetap tanggung jawab C.
Jika proses dihentikan paksa, periksa `verify.lock` serta integritas database sebelum mencoba lagi;
tidak ada retry/reset destruktif otomatis.

Evidence tersanitasi: `local-lab-setup.json`, `local-dataset.json`, `baseline-100k.json`,
dan `readiness.json`, semua di `app/evidence/access-control/`. Dataset dan credential tidak disalin.
Kelulusan ini hanya untuk lab Zhafif dengan schema/dataset tim, bukan laptop tim lain.
Tidak ada angka latency/throughput/CPU/RAM yang diklaim: benchmark API resmi masih **NOT TESTED**.

## Handoff A / C dan review

- A: toolkit/profile/test vectors belum tersedia pada `origin/main` cf2d2cc. B akan menyesuaikan
  `app/backend/service_app/crypto.py` ke API publik A ketika tersedia, tanpa menulis ulang crypto.
- A: locator HTTP tetap `legacy_row_id`; AAD tetap UUID internal protected. Migrator harus mempertahankan
  legacy ID baseline. Insert B memakai UUID4 + legacy baru di bawah advisory lock `76321017`.
- A: principal protected disimpan sebagai binding `bidx:v1:<hex>` pada akun; transaksi DB mengirim
  `app.principal=<hex>` tanpa prefix. Sinkronkan RLS/access_scope A; plain memakai pengguna sumber.
  `analyst_view` memuat REF + `age_band`. RLS/view yang dibuat skrip ini hanya untuk baseline lab lokal.
- C: checksum hasil seed42 dibandingkan dengan evidence dataset C; jangan memakai evidence lab lain
  sebagai pengganti uji API pada laptop benchmark. Gunakan endpoint/DTO/pagination/session/CSRF/audit
  yang sama pada kedua mode. Kredensial `bench_user` lokal berada di custody state, bukan source.
- PR #1 perlu review anggota lain sesuai TEAM_PLAN. Jangan merge sendiri sebelum review tersebut.
