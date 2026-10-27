# Modul C — datagen baseline (langkah 2)

## Amandemen dan generation 1M — 27 Oktober 2026

- Perubahan dataset: arahan technical meeting panitia, 27 Okt 2026; disetujui tim.
  Utama `baseline_1m` = 1.000.000 (734 sumber + 999.266 tambahan), seed 42.
  `baseline_100k` tetap titik skala/jaring pengaman; evidence benchmark awal tidak diubah.
  Target amandemen `a412ce8e4c1045c72cdf2e77af6bfe77a7ef5b5f`, 12:39:29 WIB,
  telah di-push sebelum generation. `evidence/targets_commit.json` menyimpan field aktif
  terbaru untuk kompatibilitas loader dan `history` yang mempertahankan entri awal serta amandemen.
- Generator tetap versi 1.0.0, tanpa perubahan algoritme. Kode saat generation:
  `8986fd183652f7c5b1ad55a928ae3c1a42388a43`. Hanya membuat DB baru di `pg-dpr`
  PostgreSQL 18, `127.0.0.1:5433`, koneksi baseline tanpa TLS (`sslmode=disable`).
  Tidak menyalakan/mematikan container, tidak menjalankan benchmark 1M atau migrasi A.
- Eksekusi 12:41:19–12:46:19 WIB: generation termasuk validasi penuh **182,88 detik**;
  validasi ulang penuh **78,87 detik**; provision/pemeriksaan role **0,43 detik**;
  snapshot **25,13 detik**; total termasuk pemeriksaan akhir **300,12 detik**.
- Kedua validasi lulus: 734 sumber identik; tambahan 999.266 terpisah; tidak ada duplicate/NULL
  identifier unik, pelanggaran format/relasi; distribusi/anomali sesuai kebijakan sumber.
  Checksum baseline baru cocok saat validasi ulang. Prefix 100.000 baris identik dengan baseline_100k.
  Baseline_100k serta sequence-nya diperiksa sebelum/sesudah dan tetap sama; sumber tetap sama.
- `bench_user` yang sudah ada diberi SELECT/INSERT/UPDATE dan USAGE/SELECT sequence hanya pada
  baseline baru; tidak merotasi credential. Hak dibandingkan dengan baseline_100k, DELETE/TRUNCATE
  dan DDL tetap ditolak. `scanner_user` diberi SELECT; query count dijalankan dengan SET LOCAL ROLE
  scanner_user (bukan uji autentikasi password scanner). Pembatasan CONNECT PUBLIC tetap seperti catatan lama.
- Ukuran DB saat selesai **801.609.407 byte**; tabel+indeks **793.616.384 byte**.
  Snapshot custom privat `baseline_1m.dump`: **150.429.543 byte**, header PGDMP/SHA-256 dan
  `pg_restore --list` diverifikasi; arsip memuat TABLE DATA dan SEQUENCE SET yang diperlukan.
  Snapshot ini belum merupakan uji restore 1M. Lokasi mengikuti DPR_PRIVATE_DIR di luar repo.
- Sisa disk akhir host C: **5.574.057.984 byte**. Filesystem virtual Docker melaporkan
  **979.431.227.392 byte**, tetapi ruang fisik host adalah batas penyimpanan aktual.
- Evidence: `evidence/datasets/baseline_1m.json`, `baseline_1m_preflight.json`,
  `baseline_1m_execution.json`. Pemeriksaan 17 ambang target tetap dan pengecualian arsip:
  `evidence/configuration/targets-and-public-archive.json`. Integrasi main sebelumnya bersih,
  172 test lulus/1 skip: `evidence/integration/main-merge-cf2d2cc.json`.
  Benchmark 1M menunggu perintah terpisah; hasil 100k tidak dianggap hasil 1M.

Acuan: CONTRACT, PROJECT_CONTEXT, prompt datagen, dan keputusan pengguna 26 Oktober 2026.
Target telah disahkan pada commit yang tercatat di `evidence/targets_commit.json`.

## Keputusan dan asumsi

- Tidak mengubah DB `postgres`: sumber dibaca dalam transaksi REPEATABLE READ READ ONLY;
  checksum seluruh 734 baris sebelum/sesudah generation harus sama. Ini bukan hash per sel.
- Hanya target bernama `baseline_*` yang boleh dibuat. Target yang sudah ada selalu ditolak,
  termasuk sisa generation gagal; tidak ada overwrite/truncate/drop database otomatis.
  DDL baseline yang mengandung DROP TABLE hanya dijalankan setelah CREATE DATABASE baru berhasil.
- Pertahankan ID dan seluruh 29 nilai sumber, termasuk NULL/nol awal/anomali. COPY mendukung identity
  eksplisit; set sequence sesudah COPY agar insert berikutnya tidak bertabrakan.
- Tambahan dibentuk dari karakter acak, bukan nama sumber/daftar nama publik. Nilai kategori,
  distribusi jumlah anak, dan rentang tanggal lahir dipelajari dari sumber. Putaran template
  diacak dengan seed untuk mempertahankan joint distribution kategori/anak/status/anomali;
  setiap template dipakai floor(n/734) atau ceil(n/734) kali. Putaran terakhir dapat parsial.
- Ukuran nama sintetis 24–48 karakter diturunkan dari panjang sumber dan dibatasi agar email/username
  selalu muat. Nilai nama sumber tidak dipakai sebagai nama sintetis. Semua data fixture test dibuat sendiri.
- Identifier angka: permutasi affine pada namespace digit/prefix, melompati seluruh nilai sumber.
  Keunikan diperiksa ulang pada seluruh dataset. Nomor ruangan berlanjut setelah suffix sumber,
  dan dipakai pada email/pengguna. Tidak menyalin daftar identifier ke evidence.
- Anomali tanggal dibedakan: sebelum lahir, lahir sampai sebelum usia 17, atau ≥17. Proporsi
  mengikuti template sumber; tanggal baru diacak dalam kategori tersebut. Hari lahir 29 Februari
  dijepit ke 28 Februari untuk batas interval 17 tahun. Tanggal pernikahan normal tidak melampaui
  acuan 2026-10-01. Rentang tanggal lahir seluruh sumber harus mendukung pernikahan usia ≥17.
- Kode bank tidak punya referensi resmi konsisten di sumber. Ukuran `bank_nonmodal` berarti
  kode berbeda dari kode paling sering untuk bank tersebut, **bukan validasi kode bank nasional**.
  Mode default mempertahankan distribusi pasangan bank/kode. `--no-replicate-anomalies` memakai
  kode modal dan usia pernikahan ≥17 hanya pada tambahan; 734 sumber tidak diperbaiki.
- Validasi sumber: checksum/count; validasi tambahan: format/relasi; keunikan: seluruh dataset.
  Distribusi dan anomali dilaporkan berupa jumlah kategori/deviansi agregat tanpa nilai kategori.
  Toleransi count maksimal satu putaran sumber untuk jumlah tambahan yang tidak habis dibagi 734.
- `age_band` belum ditambahkan ke schema plaintext (schema baseline tetap milik kontrak).
  Langkah residual/migrasi memakai usia tahun penuh pada 2026-10-01 dan kelompok 10 tahun.

## Komponen lama dan hak akses

- `scripts/scale_lab.py` dipertahankan sebagai generator historis skema aplikasi lama; baseline
  kontrak 100k memakai `python -m datagen`. Tidak memanggil migrasi/proteksi aplikasi lama.
- Pola dump custom dan pemisahan credential dari argv pada `scripts/backup.py` dipakai kembali
  sebagai dasar operasi snapshot. Implementasi langsung memakai psycopg v3 dan subprocess supaya
  tidak memuat SQLAlchemy, kunci aplikasi, atau side effect aplikasi lama. Snapshot memakai
  pg_dump 18 dari container; file biner langsung melalui stdout handle, tanpa redirection PowerShell.
- `scripts/benchmark.py` dan semua evidence historis dipertahankan. Pemilihan ulang utilitas metrik
  dilakukan pada langkah 3, lalu dicatat di `benchmark/NOTES.md`; belum digantikan oleh hasil baru.
- `bench_user` baru memakai SCRAM-SHA-256 dari libpq, tanpa password literal SQL. Role lama tidak
  dirotasi passwordnya; privilege elevated/membership yang tidak diharapkan menyebabkan gagal.
  Hanya SELECT/INSERT/UPDATE dan sequence pada baseline. `scanner_user` hanya diberi SELECT/USAGE/CONNECT;
  tidak mengubah passwordnya. Hak PUBLIC pada database baseline baru dicabut, sumber tidak diubah.
- PostgreSQL tidak punya DENY role terhadap grant PUBLIC: CONNECT/metadata ke database lain dapat
  masih diwarisi PUBLIC. Tidak memberi bench_user akses data sumber; diuji lewat has_table_privilege.
  Menutup CONNECT lintas DB memerlukan aturan pg_hba dari A, bukan perubahan ACL database `postgres`.

## Penyimpanan, reproduksi, dan batas

- Ringkasan kecil: `evidence/datasets/<db>.json` (commit); salinan kompatibilitas prompt:
  `results/bench/datasets/<db>.json` (lokal). Baseline checksum saat generation disimpan terpisah
  sehingga validate berikutnya tidak bisa mengesahkan perubahan data tanpa mendeteksinya.
- Snapshot plaintext/custom hanya di bawah `DPR_PRIVATE_DIR` di luar repo; pembuatan eksklusif,
  tidak menimpa file lama. Rekam ukuran/SHA-256 artefak tanpa isi/path rahasia. Ini snapshot
  baseline plaintext, bukan backup protected, bukan bukti restore; drill backup/restore langkah 3.
- Admin dapat menggunakan credential env container lokal yang sudah ada tanpa mencetak nilainya.
  Password bench baru dibuat acak dan disimpan DPAPI sebagai PSCredential di direktori privat,
  dibaca PowerShell ke env saat diperlukan. Bukan password di source/history/chat.
  DPAPI hanya dapat dibuka identitas Windows/mesin yang sama; ini mekanisme lab, bukan key plane A.
- Semua error CLI generik; metadata tidak berisi DSN, SQL error, nilai record, password, atau token.
  Dataset checksum agregat dan snapshot checksum bukan pengganti autentikasi backup protected.
- Hasil test/generation/provision/snapshot yang benar-benar dijalankan dirujuk melalui evidence.
  Belum ada klaim benchmark, migrasi protected, restore, atau evaluasi scanner pada langkah ini.

## Hasil langkah 2 yang dijalankan

- PostgreSQL aktual: 18.6; `baseline_100k` dibuat seed 42, total 100.000 (734 sumber + 99.266 tambahan).
  Validasi penuh dan validasi ulang lulus: sumber tidak berubah, checksum baseline cocok, tidak ada
  duplicate/NULL pada identifier unik, pelanggaran format atau relasi tambahan.
- Source mempunyai 42 tanggal pernikahan sebelum lahir; dengan batas kalender ulang tahun ke-17,
  total 132 sebelum usia 17 (90 setelah lahir + 42 sebelum lahir). PROJECT_CONTEXT menyebut 131;
  query independen PostgreSQL `tanggal_pernikahan < tanggal_lahir + interval '17 years'` menghasilkan
  132. Angka tidak dipaksa cocok; catat perbedaan konvensi batas usia ini, sumber tetap dipertahankan.
- Role bench_user berhasil autentikasi, grant minimum dan larangan sumber/DDL diperiksa;
  scanner_user SELECT-only baseline diperiksa. Semua nilai boolean pada `roles.checks` berarti
  assertion lulus, dengan label `_allowed`/`_denied` menjelaskan hak yang diuji.
- Snapshot custom di luar repo berukuran 14.996.532 byte; header PGDMP dan `pg_restore --list`
  dari container diverifikasi. Ini validasi format archive, **belum** drill restore langkah 3.
- Suite datagen: 25 test lulus; ringkasan mesin `evidence/datasets/datagen-tests.json`, raw JUnit lokal
  `results/datagen/unit-tests.xml`. Hasil dataset/role/snapshot ada di
  `evidence/datasets/baseline_100k.json`.
