# Modul C — baseline awal level DB, langkah 3

## Sesi utama 1M dan pemeriksaan silang — 27 Oktober 2026

- Parameter sama seperti baseline awal 100k: 7 skenario ×3 run, concurrency8,
  measurement60 detik, warmup10 detik, TCP tanpa TLS, bench_user. Metode tetap
  sesi baseline awal, terpisah dari B–P–P–B. Workload manifest dan timed worker
  tidak diubah; benchmark versi1.1.0 hanya memperluas pilihan dataset dan output.
- Dataset baseline_1m diverifikasi terhadap checksum generation dan sequence di
  luar waktu ukur, termasuk setelah setiap run. Korpus 2048 profil dan64 halaman
  dibuat seed42 secara terpisah untuk populasi1M; ini bukan pool ID yang identik
  dengan 100k. Tabel perbandingan skala menggambarkan dua sesi awal terpisah.
- Ambang ruang fisik Windows10 GB diperiksa sebelum 1M serta setiap run/restore;
  kapasitas virtual Docker tidak dipakai untuk menggantikannya. Saat awal sesi
  Docker Desktop tidak aktif; dinyalakan sekali, kemudian pg-dpr yang sama dijalankan.
  Tidak ada container lain yang dinyalakan. Pemanasan cache tetap melalui integrity
  scan, VACUUM ANALYZE dan warmup; tidak ada flush cache atau klaim cold-cache.
- Pgbench18.6 berada di pg-dpr, TCP127.0.0.1:5432,8 koneksi/8 thread, prepared,
  3×60 detik dan pemanasan terpisah10 detik. Custom SELECT mengembalikan30 field
  yang sama. Seluruh2048 kunci diambil dari corpus100k asli dengan hash yang sama,
  dipilih acak uniform seed42 (PRNG/urutan berbeda dari Python). CASE seimbang
  memilih nilai integer; lpad mengembalikan nol awal ke14 digit. Query berparameter,
  tanpa CREATE/INSERT tabel pgbench. Script privat hanya di DPR_PRIVATE_DIR dan
  dikirim stdin; log transaksi tidak memuat key, disalin ke results sebelum dihapus
  dari container. Password hanya di env Docker exec, bukan argv atau metadata.
- Pgbench memakai client C dalam VM; Python berada di Windows melalui port5433,
  melakukan konversi object/fetch, validasi hasil tiap request dan loggingCSV.
  Pgbench tidak memvalidasi isi per-request; probe2048 key dilakukan terpisah.
  Selisih mencakup overhead client dan jalur jaringan/penempatan, sehingga tidak
  dapat diatribusikan seluruhnya pada interpreter Python. CPU psutil dibagi
  jumlah logicalCPU untuk persentase kapasitas mesin; utilisasi rendah bukan bukti
  yang menyingkirkan batas GIL/satu inti. Kesimpulan bottleneck mengikuti data aktual.
  Rujukan primer: https://www.postgresql.org/docs/18/pgbench.html (custom scripts,
  prepared protocol, per-transaction logs).
- Perubahan scanner1.2 dilakukan setelah pengukuran1M dan pgbench berakhir.
  Kegagalan setiap fase dicatat tanpa retry otomatis, fase independen dilanjutkan.

Penetapan sesi: 27 Oktober 2026 WIB. Acuan target yang sudah disahkan:
`docs/targets.md`, bukti commit di `evidence/targets_commit.json`.

## Tujuan dan keputusan tim

- Ini **baseline awal**, sesi tersendiri; bukan eksperimen berpasangan B–P–P–B.
  Tujuh skenario, masing-masing 3 run, concurrency 8, measurement window 60 detik,
  warmup 10 detik/run tidak masuk sampel. Backup/restore 3 run terpisah.
- Keputusan pengguna: semua DB `baseline_100k`, `protected_734`, `protected_100k`
  berada di instance **pg-dpr**, `127.0.0.1:5433`. OpenBao berasal dari
  `infra/compose.yaml` Modul A. PostgreSQL opsional 5434 dan PostgreSQL 17 Compose
  root **tidak digunakan** untuk benchmark. Tidak menjalankan/memigrasikan protected sekarang.
- Baseline ini memakai TCP **tanpa TLS**, dipaksa `sslmode=disable` dan diperiksa
  dengan `pg_stat_ssl`. Tidak menjadi bukti TLS atau pengukuran API.
- Pengguna melaporkan laptop memakai charger, mode daya **Best performance**, tidak
  ada aplikasi berat lain, container lain dihentikan. Metadata memisahkan pernyataan
  tersebut dari observasi: daftar container, battery.power_plugged dan power scheme.
  Power scheme Windows (misalnya OEM Acer) bukan bukti langsung setting overlay
  Best performance. Runner menolak battery.power_plugged=false bila sensor tersedia.

## Komponen lama yang dipakai ulang dan digantikan

- `scripts/benchmark.py` dipertahankan; hasil 734/10k, sequential 80/20/PG17 tetap
  evidence historis. Baseline kontrak baru dijalankan melalui `python -m benchmark`.
- Mengadaptasi pola psutil CPU/RSS, median `statistics.median`, pengukuran ukuran DB,
  serta subprocess dump/restore dan pemisahan credential dari argv pada skrip lama.
  Tidak mengimpor entry point lama karena ia memuat config/crypto/skema aplikasi lama.
- Percentile baru memakai interpolasi linear (posisi `(n-1)*q`), bukan pembulatan
  indeks ke bawah utilitas lama. Unit test membuktikan percentile dan median antar-run.
- Kolektor mengganti pemantauan native process tree PG dengan `docker stats
  --no-stream` pada pg-dpr, plus psutil pada proses client. Tidak menghapus file lama.

## Workload dan kesetaraan bisnis

- Definisi dibekukan pada `benchmark/workloads.yaml` dan commit kode sebelum run.
  Pool tetap 2.048 profil, termasuk ID terbesar, dan 64 halaman × 50 anggota dipilih
  seed 42. Semua kunci/expected rows/template insert hanya di luar repo melalui
  `DPR_PRIVATE_DIR/benchmark/baseline_100k_keys_v1.json`; evidence hanya digest agregat
  file dan jumlah. Corpus yang sama wajib dipakai saat protected diuji nanti.
- Exact NIK/email dan read_profile mengembalikan seluruh 29 field sumber + ID bisnis;
  validator memeriksa kesamaan seluruh hasil. List mengambil `id,nama,jenis_kelamin`,
  pagination by ID, 50 anggota; seluruh hasil dibanding expected page.
- Mixed memakai siklus 100 operasi diacak deterministik per worker: 20 NIK, 20 email,
  20 profile, 10 list, 15 update, 15 insert = 70% baca / 30% tulis. Fragmen terakhir
  siklus dapat membuat rasio aktual sedikit berbeda; jumlah per operasi disimpan.
- Satu koneksi persistent psycopg per worker, auto prepared statement threshold 5.
  Stream operasi dan kunci di-reset sesudah warmup, seed/prefix worker sama antar-run.
  Timings mencakup SQL, fetch, validasi hasil, dan rollback untuk operasi tulis.
- UPDATE handphone dan INSERT dibungkus transaksi **force_rollback**. Insert memakai
  `OVERRIDING SYSTEM VALUE`, ID negatif khusus per worker, sehingga sequence identity
  tidak maju (ROLLBACK saja tidak mengembalikan nextval). Template tambahan sintetis
  dari generator C diperiksa terhadap identifier unik seluruh baseline sebelum run.
- Functional probe seluruh operasi/worker dijalankan di luar waktu terukur. Count,
  checksum seluruh baris, dan state sequence dibandingkan sebelum/sesudah probe
  serta sesudah setiap run. Sumber postgres/734 hanya dibaca dan dicek checksum.

## Pengukuran dan batas interpretasi

- Closed loop: setiap worker mulai request berikutnya setelah request sebelumnya
  selesai. Tidak memulai request baru setelah window 60 detik; request terakhir
  di-drain. Throughput = sukses/durasi aktual sampai worker selesai, termasuk flush
  buffer raw terakhir. Durasi aktual dan window nominal keduanya disimpan.
- Latency tiap operasi ditangkap sebelum penulisan baris CSV. Throughput dan CPU/RAM
  client tetap mencakup overhead logging/collector; latencies berada di RAM per run.
  RAM client bukan working set aplikasi bisnis saja dan bergantung jumlah sampel.
- p50/p95/p99/mean utama mencakup semua request, termasuk gagal. Statistik sukses
  saja tersedia terpisah; timeout, exception, hasil salah dihitung error. Error
  raw hanya kode generik tanpa SQL/parameter/driver message. Warmup error dilaporkan.
- Ringkasan skenario = median statistik masing-masing run, bukan percentile gabungan.
  P01–P03 DB/API berstatus BELUM DIUJI sampai ada kondisi protected yang sebanding;
  baseline sendiri tidak membuktikan target overhead terpenuhi.
- Docker stats dipanggil serial berkala (jeda 2 detik setelah tiap respons); periode
  aktual termasuk waktu Docker CLI. CPU 100% berarti satu logical CPU, dapat >100%.
  CPU/RAM container dan client disimpan mentah; missing sample bukan angka nol.
  Ringkasan resource menyimpan median/peak per run dan median resource antar-run.
- Sebelum setiap run, VACUUM (ANALYZE) biasa hanya pada baseline, melalui admin di luar
  warmup/measurement. Tidak memakai VACUUM FULL, tidak flush OS cache/checkpoint.
  Integrity scan dan maintenance menghangatkan cache; ini pengukuran warm-cache.
  Write rollback masih menghasilkan MVCC/WAL dan aktivitas autovacuum; ukuran DB,
  tabel/indeks serta konfigurasi autovacuum dicatat. Dataset logical tetap sama.
- Komponen DB dan client berada di laptop/Docker Desktop yang sama. Tidak mengukur
  jaringan produksi, TLS, autentikasi HTTP, OpenBao, atau kapasitas produksi.

## Backup/restore baseline

- Gunakan pg_dump/pg_restore **18** di dalam pg-dpr, Unix socket tanpa TLS, role admin;
  workload timed tetap bench_user. Client lokal PostgreSQL 17 tidak digunakan.
- Setiap run membuat dump custom baru di DPR_PRIVATE_DIR, melalui handle biner
  stdout (tanpa redirection PowerShell). Backup time termasuk Docker exec, pg_dump,
  dan penulisan file; ini baseline plaintext, bukan backup protected terenkripsi.
- Restore selalu ke nama unik `bench_restore_<run>_<random12hex>`, CREATE database
  baru template0; pg_restore --exit-on-error --single-transaction --no-owner --no-acl.
  Restore time termasuk CREATE + restore, tidak termasuk validasi/cleanup.
- Validasi seluruh count/checksum/sequence hasil restore. Hanya DB sementara yang
  dibuat run itu dihapus setelah validasi lulus; tidak ada overwrite/drop baseline
  atau postgres. Dump dihapus setelah sukses kecuali --keep; gagal dipertahankan
  secara privat untuk investigasi. Ringkasan tidak berisi dump atau nilai data.

## Artefak

- Raw: `results/bench/before/<scenario>/run_<n>/requests_worker_<n>.csv`, resources.csv,
  env.json, run_summaries.json/CSV, summary.json/CSV, dan backup_restore/ lokal.
- Ringkasan kecil: `evidence/benchmark/baseline/`, di-commit. File dataset/targets
  sebelumnya tidak diubah. Tidak menyimpan DSN, password, token, atau kunci lookup
  pribadi ke metadata/CSV/log/repo. Kredensial dibaca dari env proses saja.

## Hasil sesi 27 Oktober 2026 (sudah dijalankan)

- Kode/workload dibekukan dan di-push pada `776d420845d17ace5d96aacf702a17d7e562d0d4`
  sebelum pengukuran. Metadata mulai 10:43:37 WIB; pengukuran utama selesai
  11:10:38 WIB, backup/restore selesai 11:11:24 WIB. Ini baseline awal, bukan B–P–P–B.
- 42 unit/regression test benchmark + datagen lulus, serta 48 functional probe
  DB nyata lulus sebelum measurement. Sebanyak 21 run terukur menghasilkan
  **2.143.577 request, 0 error, 0 warmup error**. Semua run valid dan telemetry lengkap:
  **336 sampel resource, 0 gagal**. Sensor charger true; hanya pg-dpr teramati berjalan.
- Median antar-run (bukan percentile gabungan):

| Skenario | p50 ms | p95 ms | Sukses/detik | Error |
| --- | ---: | ---: | ---: | ---: |
| read_by_nik | 3,8067 | 7,7971 | 1835,2674 | 0% |
| read_by_email | 3,6632 | 6,7605 | 2010,0416 | 0% |
| read_profile | 3,6662 | 6,8309 | 1993,4124 | 0% |
| list_page | 2,6998 | 5,2452 | 2580,0420 | 0% |
| update_contact | 5,6417 | 9,4342 | 1297,5272 | 0% |
| insert_member | 9,3570 | 14,2481 | 807,1745 | 0% |
| mixed | 4,3451 | 13,2371 | 1318,6113 | 0% |

- Backup detik per run: 3,731489 / 3,313530 / 2,974606; **median 3,313530**.
  Restore detik per run: 3,926249 / 2,858266 / 2,983256; **median 2,983256**.
  Dump masing-masing 14.996.532 byte. Ketiga restore mempunyai 100.000 baris,
  checksum seluruh data dan sequence sesuai; ketiga DB sementara dan dump privat
  run ini dibersihkan setelah sukses. Snapshot datagen awal tetap dipertahankan.
- Canonical checksum baseline tetap
  `e6cdc975a397e1e1d2020bc476a51103d1799c38e28a1c35f6284564aef698ff`;
  checksum sumber 734 tetap
  `5113038953aea9383f600de725b4267ecbf93de47c2a603a68bde6ad7e5c17e8`.
  Sequence baseline tetap 100.000/is_called=true.
- Audit ulang CSV mentah memeriksa jumlah request/error/jenis operasi, urutan worker,
  jendela timestamp di luar warmup, header/value yang dibatasi, jumlah resource,
  dan menghitung ulang percentile/mean/throughput. Seluruh 21 run cocok. Manifest
  SHA-256 lokal mencakup **189 file raw, 134.523.152 byte**, tidak di-commit.
- Hasil mesin: `summary.json/CSV`, `run_summaries.json/CSV`, `env.json`,
  `backup_restore.json`, `backup_restore/runs.csv`, `raw_validation.json` pada
  `evidence/benchmark/baseline/`. P01–P03 protected/API tetap **BELUM DIUJI**.

## Hasil sesi 1M dan pgbench yang dijalankan ? 27 Oktober 2026

Kode sebelum run: `cfd703b8080a1c7bd6b574779e6e8e1dc9441a32`. Semua fase lulus tanpa retry.

Ini perbandingan skala dua sesi baseline awal, bukan penilaian P01?P03 plain/protected. Semua median dihitung antar-run.

| Skenario | 100k p50 / p95 (ms) | 1M p50 / p95 (ms) | 100k req/s | 1M req/s | Error 100k / 1M |
|---|---:|---:|---:|---:|---:|
| read_by_nik | 3.807 / 7.797 | 4.445 / 15.400 | 1835.267 | 1366.313 | 0.0% / 0.0% |
| read_by_email | 3.663 / 6.761 | 3.471 / 6.331 | 2010.042 | 2122.647 | 0.0% / 0.0% |
| read_profile | 3.666 / 6.831 | 3.429 / 6.185 | 1993.412 | 2163.505 | 0.0% / 0.0% |
| list_page | 2.700 / 5.245 | 2.526 / 4.557 | 2580.042 | 2844.668 | 0.0% / 0.0% |
| update_contact | 5.642 / 9.434 | 5.582 / 9.579 | 1297.527 | 1301.950 | 0.0% / 0.0% |
| insert_member | 9.357 / 14.248 | 9.114 / 13.653 | 807.174 | 825.969 | 0.0% / 0.0% |
| mixed | 4.345 / 13.237 | 3.932 / 11.578 | 1318.611 | 1481.665 | 0.0% / 0.0% |

1M: 2,134,636 request terukur, 0 error dan seluruh21 run lulus checksum/sequence. Variasi antar-run tetap disimpan; misalnya email run1 lebih lambat daripada run2/3. Tidak membuang outlier atau mengulang untuk memperbaiki angka.
Backup/restore1M: median 23.389305 / 27.942557 detik. Ketiga restore berisi1.000.000 baris dengan checksum/sequence sesuai; tiga DB dan dump sementara yang dibuat runner sudah dihapus. Snapshot privat generation tetap dipertahankan.
Raw1M: 133.678.973 byte CSV menjadi28.953.920 byte gzip level1. Hash dekompresi cocok dengan setiap file asli sebelum CSV milik sesi ini diganti gzip. Audit seluruh request menghitung ulang persentil/count/throughput dari raw.

| Pemeriksaan silang read_by_nik 100k | Python asli | pgbench (median3 run) |
|---|---:|---:|
| p50 (ms) | 3.806700 | 0.094000 |
| p95 (ms) | 7.797060 | 0.142000 |
| Mean (ms) | 4.327669 | 0.149000 |
| Throughput (req/s) | 1835.267446 | 53661.138857 |
| Error rate | 0.000000 | 0.000000 |

Rasio throughput pgbench/Python = 29.239?. Hash corpus2048 key identik; semua3 run pgbench tanpa error, data/sequence100k tetap. Query mengembalikan30 field; pgbench memakai clientC, jalurTCP di container dan tidak mengonversi/membandingkan field Python tiap request. Angka tersebut mencakup overhead client, validasi/logging dan perbedaan transport/penempatan, bukan estimasi murni overhead interpreter.
CPU client1M dari psutil: median per skenario 12.575?16.169% kapasitas8 logicalCPU; peak sampel tertinggi 17.988%. CPU keseluruhan mesin tidak jenuh pada sampel, tetapi ini tidak membuktikan ketiadaan batas GIL/satu inti atau bottleneck transport. CPU client100k read_by_nik historis 15.094% kapasitas mesin. Resource mentah berada dalam gzip; ringkasan client_cpu.json menyimpan definisi dan cakupan.
Evidence: evidence/benchmark/baseline_1m/ (summary, per-run, env, backup_restore, raw_validation, client_cpu); crosscheck_pgbench.json; session_1m_crosscheck.json. Raw pgbench di results/bench/crosscheck_pgbench/ tanpa key; seluruh log sementara container serta script privat sudah dihapus.

## Portabilitas test pada paket pengumpulan — 28 Oktober 2026

Unit test environment memakai sensor baterai buatan sendiri untuk kasus charger
tersambung dan tidak tersambung. Guard charger pada runtime tetap diuji menolak
kondisi tidak tersambung; benchmark aktual dan angka evidence tidak berubah.
