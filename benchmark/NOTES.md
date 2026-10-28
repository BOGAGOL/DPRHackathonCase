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

## Investigasi overhead runner — 27 Oktober 2026

Ini diagnostik terbatas, **bukan rerun benchmark resmi**. Kode runner/adapter dan
seluruh hasil baseline 100k/1M tetap. Perintah: `python -m benchmark.diagnose_overhead`
(venv benchmark; env BENCH_DATABASE_URL dan DPR_PRIVATE_DIR yang sama). Request
read-only: 2.000 **total** per concurrency 1/8, warmup 32 per worker; tambahan 32
EXPLAIN per database. Corpus lookup privat asli dipakai kembali, tanpa generation.
Raw aman di `results/bench/diagnostics/`; hasil `evidence/benchmark/runner_overhead.json`.

Audit `one_run`/`worker_run`/`PlaintextAdapter`: satu koneksi persisten per worker,
dibuka sebelum thread/measurement; bukan connect setiap request. CSV per worker
buffer 256 KiB, tanpa flush/fsync per request, ditulis setelah latency dicatat.
Validasi satu tuple 30 field; expected tuple dan komposisi query dibuat per request.
Sorting percentile dan checksum seluruh DB berada di luar measurement. Tidak ada
lock bersama eksplisit dalam request path. Delapan backend tetap, masing-masing
memiliki satu prepared statement setelah warmup. Tidak ditemukan cacat implementasi
yang mengharuskan perbaikan/rerun; tidak ada benchmark resmi yang diulang.

Rata-rata komponen dari sampel diagnostik (ms; p50/p95 tersimpan juga di JSON):

| Komponen | concurrency 1 | concurrency 8 |
|---|---:|---:|
| psycopg.execute | 0.737483 | 3.309983 |
| psycopg.fetchall | 0.006094 | 0.009216 |
| kode adapter di luar driver | 0.030470 | 0.049302 |
| end-to-end adapter | 0.774047 | 3.368501 |
| bookkeeping + buffered CSV, di luar latency | 0.012643 | 0.020303 |

P50/p95 request: c1 **0.677650/1.309210 ms**, c8 **3.239200/5.569475 ms**,
masing-masing 0 error. Timer proxy menambah sedikit overhead. Komponen mean
menjumlah; percentile komponen tidak boleh dijumlah/dikurangkan. CSV diagnostik
berisi timer execute/fetch/adapter/latency aman; bookkeeping setelah penulisan
CSV hanya diagregasi di JSON (kolom raw itu kosong), tanpa parameter bisnis. `execute` mencakup
psycopg/libpq, round trip Windows→Docker forwarded port, scheduling dan server;
ini **bukan pengukuran CPU interpreter Python saja**. Runtime Python 3.11.3,
psycopg 3.3.6 dengan libpq implementation `binary`, waiting function module
`psycopg.waiting`, switch interval GIL default 5 ms (tidak diubah). Thread CPU terukur 0,5000 s
(c1) dan 1,1875 s (c8). Tidak ada lock profiler, sehingga GIL/per-core scheduling
belum dapat dipisahkan secara kuantitatif. Tidak menyimpulkan seluruh selisih
29,24× pgbench berasal dari GIL. pgbench berjalan lewat loopback di container dan
tidak melakukan konversi serta validasi tuple Python. Sampel 2.000 request ini
lebih singkat dan kondisi cache/waktu berbeda dari sesi resmi; tidak menggantikannya.

EXPLAIN ANALYZE terpisah (TIMING ON; overhead instrumentasi termasuk): server
100k execution mean/p50/p95 **0.031469/0.029500/0.051600 ms**; 1M
**1.076281/1.012000/1.925400 ms**. Planning dilaporkan terpisah. Plan lengkap
tidak disimpan karena Index Cond dapat mengandung NIK; hanya node/index name,
timing dan aggregate buffer counts keluar. Tidak mengurangkan p50 EXPLAIN dari
p50 client seolah sampelnya berpasangan.

P95 resmi NIK 7,797→15,400 ms konsisten dengan working set yang membesar:
NIK index 100k **5.336 MiB**, 1M **44.023 MiB**; shared_buffers **128 MiB**, global
untuk instance. **Index NIK 1M sendiri masih muat**; total index 279,18 MiB dan
heap 499,68 MiB bersaing memperebutkan buffer, dibanding total heap+index 100k
91,95 MiB. Snapshot statistik saat investigasi: NIK index hit 99,9982% vs 97,8057%,
heap hit 99,9397% vs 73,5230% (100k vs 1M). EXPLAIN 100k 128 hit/0 read block;
1M 61 hit/97 read block. Ini mendukung cache misses sebagai faktor yang masuk
akal, **bukan bukti sebab tunggal p95 historis**: counters kumulatif mencampur
benchmark, integrity scan dan pgbench; hit OS cache bukan hit shared buffers.
Tidak mereset statistik, membersihkan cache, menjalankan VACUUM atau mengubah konfigurasi.

`pg_stat_statements` belum terpasang di kedua baseline; pembacaan admin memastikan
shared_preload_libraries kosong dan track_io_timing off. Tiga probe metadata awal
gagal karena hak baca shared_preload_libraries dibatasi/row disembunyikan dari
bench_user; diperbaiki menjadi nilai unavailable. Semua terjadi **sebelum** loop
diagnostik; hanya satu batch c1/c8 berhasil dijalankan. Tidak mengubah role/config.

Usulan untuk eksperimen berpasangan nanti: tampilkan **db_time_mean_ms = delta
total_exec_time / delta calls** dari pg_stat_statements, berdampingan dengan
latency bisnis end-to-end yang tetap menjadi target P01. Ambil delta per dbid,
userid, queryid dan top-level pada interval measurement yang terisolasi; catat
planning terpisah, reset/eviction dan sesi lain. Ini mean server, bukan p95 atau
waktu crypto/round trip. Pengaktifan membutuhkan setup/restart yang disepakati
sebelum **kedua mode**; jangan mengubahnya di tengah B-P-P-B atau menyebut baseline
lama sudah mempunyai db_time. Belum diaktifkan pada sesi ini.

Rujukan primer untuk interpretasi: [PostgreSQL 18 cumulative statistics](https://www.postgresql.org/docs/18/monitoring-stats.html),
[pg_stat_statements](https://www.postgresql.org/docs/18/pgstatstatements.html),
[Psycopg concurrent connections](https://www.psycopg.org/psycopg3/docs/advanced/async.html).

## Audit gangguan sumber daya sesi 1M — 27 Oktober 2026

Tambahan informasi pengguna: charger sempat dicabut sekitar satu menit, waktunya
diingat berada di sekitar **19:00–19:21 WIB**. Ini diperlakukan sebagai rentang
ketidakpastian waktu kejadian, bukan pemadaman selama 21 menit. Pemeriksaan hanya
membaca file hasil lama dan System event log Windows; **tidak ada benchmark,
diagnostik request DB, backup atau restore yang diulang**.

`Get-WinEvent`, provider `Microsoft-Windows-Kernel-Power`, event **105** memberi
bukti yang lebih tepat:

- Record **26748**: AC=true **18:15:35.383355 WIB**; tidak ada event AC=false
  berikutnya sampai 19:18:04. Seluruh pengukuran workload 1M berada di antaranya.
- Record **27150**: AC=false **19:18:04.086749 WIB**.
- Record **27177**: AC=true **19:27:03.460341 WIB**.
- Interval baterai menurut log: **539,374 detik (8 menit 59,374 detik)**.
  Angka ini berbeda dari ingatan durasi sekitar satu menit; keduanya dicatat,
  tidak mengganti timestamp log dengan perkiraan pengguna. Windows memakai
  SE Asia Standard Time; evidence menyimpan UTC dan +07:00.
- Event 506/507 pada 19:18:06.113 / 19:18:52.245 mencatat sesi Modern Standby
  sekitar 46,132 detik. Payload exit menyatakan **SleepEntered=false**,
  SleepDurationInUs=0 dan DripsResidencyInUs=0; **tidak menyimpulkan CPU/VM
  berhenti selama 46 detik** hanya dari judul event.

Waktu berikut adalah **measurement**, WIB, tanggal 27 Oktober; warmup 10 detik
sebelumnya tidak dihitung. Akhir = started_at_utc + elapsed_s, termasuk drain
worker; completed_at_utc adalah bookkeeping sesudah measurement. Rentang
berikut ditampilkan hingga detik; CSV/JSON mempertahankan subdetik.

| Skenario | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| read_by_nik | 18:34:40–18:35:40 | 18:37:11–18:38:11 | 18:39:40–18:40:40 |
| read_by_email | 18:41:58–18:42:58 | 18:44:10–18:45:10 | 18:46:00–18:47:00 |
| read_profile | 18:47:49–18:48:49 | 18:49:39–18:50:39 | 18:51:29–18:52:29 |
| list_page | 18:53:20–18:54:20 | 18:55:09–18:56:09 | 18:56:59–18:57:59 |
| update_contact | 18:58:47–18:59:47 | 19:00:37–19:01:37 | 19:02:28–19:03:28 |
| insert_member | 19:04:17–19:05:17 | 19:06:06–19:07:06 | 19:07:55–19:08:55 |
| mixed | 19:09:44–19:10:44 | 19:11:37–19:12:37 | 19:13:30–19:14:30 |

**Tidak satu pun dari 21 measurement/warmup beririsan dengan interval baterai
yang tercatat.** Measurement terakhir selesai **19:14:30.091702**, yaitu
**213,995 detik sebelum** AC=false. P95 NIK yang tinggi pada 18:34–18:40 dan
email run 1 pada 18:41 tidak disebabkan oleh kejadian AC=false 19:18 ini.
Ini bukan bukti semua penyebab variasi kinerja sudah diketahui.

Delapan run yang masuk rentang ingatan 19:00–19:21: update_contact 2/3,
insert_member 1/2/3, mixed 1/2/3. Perbandingan dengan run lain dalam skenario
yang sama (run 1 update di luar rentang juga ditampilkan):

| Skenario/run | p50 ms | p95 ms | sukses/s | CPU client median % satu inti | CPU DB median % satu inti |
|---|---:|---:|---:|---:|---:|
| update_contact 1 | 5.4326 | 8.9152 | 1339.961 | 131.00 | 139.44 |
| update_contact 2 | 5.5822 | 9.5792 | 1301.950 | 129.35 | 131.99 |
| update_contact 3 | 5.6225 | 10.7153 | 1241.546 | 122.25 | 136.77 |
| insert_member 1 | 9.1135 | 13.8392 | 825.969 | 129.30 | 84.565 |
| insert_member 2 | 9.0368 | 13.5223 | 838.627 | 130.55 | 85.435 |
| insert_member 3 | 9.2498 | 13.6529 | 822.739 | 127.75 | 88.36 |
| mixed 1 | 3.9324 | 11.5776 | 1481.665 | 126.25 | 95.62 |
| mixed 2 | 4.0812 | 12.3140 | 1400.017 | 120.25 | 103.975 |
| mixed 3 | 3.8358 | 11.1521 | 1539.665 | 129.10 | 93.16 |

Contoh variasi terhadap median dua peer: update run 3 p95 +15,88%, throughput
-6,01%; mixed run 2 p95 +8,35%, throughput -7,32%. Insert relatif stabil
(p95 13,5223–13,8392 ms). Semua masih AC menurut urutan event, jadi variasi
ini **tidak dapat diatribusikan pada unplug 19:18**. Seluruh perbandingan
persentase 21 run dan median/peak CPU/RAM ada di power_run_timeline.csv/JSON.

Ada **129 sampel resource** pada delapan run dalam rentang ingatan, tanpa
sampling gagal; last sample timestamp **19:14:30.030438**. Client RSS peak
sekitar 58,5–61,5 MB desimal, DB RAM peak sekitar 826,8–1051,7 MB pada delapan
run tersebut. CPU % satu inti dapat >100 karena multi-thread; persen kapasitas
mesin dibagi 8. Collector tidak mencatat AC state, frekuensi CPU atau temperatur.
**Tidak ada sampel CPU/RAM benchmark saat interval baterai yang terkonfirmasi**;
backup/pgbench tidak punya collector setara. Tidak mengisi data itu dengan nol
atau memakai sampel lebih awal seolah-olah berasal dari waktu kejadian.

### Fase sesudah workload yang benar-benar beririsan

| Backup/restore | Mulai WIB | Backup s | Restore s | Paparan baterai saat pengukuran |
|---|---|---:|---:|---|
| Run 1 | 19:15:42.857930 | 23.389305 | 28.247456 | Tidak |
| Run 2 | 19:17:15.416273 | 24.110519 | 27.942557 | Sekitar 3,383 s terakhir restore, sampai sekitar 19:18:07.469349 |
| Run 3 | 19:19:10.229176 | 21.587495 | 24.076759 | Seluruh backup dan restore, sampai sekitar 19:19:55.893430 |

Batas tahap backup/restore diturunkan dari start + durasi monotonic; overhead
peralihan tidak punya timestamp terpisah, sehingga overlap 3,383 s adalah
perkiraan, bukan presisi event log. Run 3 justru lebih cepat; ini tidak
membuktikan baterai mempercepat, atau bahwa pengaruh daya nol. Run 2 juga
beririsan dengan awal sesi event 506/507 saat restore/validasi; tidak dapat
memisahkan pengaruh screen/power/OS dari durasi saja. Validasi count/checksum/
sequence tiga restore tetap lulus; **kualifikasi lingkungan untuk timing run 2/3
ditandai ENVIRONMENT_DEVIATION**, tanpa menghapus data atau mengubah median.

Ketiga run pgbench pada baseline_100k juga seluruhnya berada pada baterai.
Batas ini dibaca dari first/last transaction completion di log tiap thread,
bukan timestamp file atau asumsi lama proses:

| pgbench | Jendela transaksi WIB | p50 / p95 ms | sukses/s |
|---|---|---:|---:|
| Run 1 | 19:21:46.446443–19:22:46.440369 | 0.100 / 0.163 | 45550.193 |
| Run 2 | 19:23:08.034076–19:24:08.044026 | 0.094 / 0.142 | 53736.931 |
| Run 3 | 19:24:39.815275–19:25:39.812920 | 0.092 / 0.139 | 53661.139 |

Run 1 lebih lambat dari run 2/3, tetapi ketiganya sama-sama pada baterai; tidak
bisa menyatakan perbedaannya disebabkan transisi AC. Semua 0 error. **Perbandingan
pgbench vs Python baseline 100k memiliki confound tambahan: baterai vs AC**.
Rasio 29,24× tetap angka deskriptif hasil lama, tidak boleh dipakai mengisolasi
overhead Python atau dianggap perbandingan dengan kondisi daya yang sama.

Evidence: power_events.json, power_incident.json, power_run_timeline.csv dalam
evidence/benchmark/baseline_1m/. Metadata env, per-run, summary, backup_restore,
session dan crosscheck diberi post_run_power_audit; flag charger=true asli
dipertahankan sebagai **observasi preflight/laporan awal**, bukan verifikasi AC
kontinu. Status PASSED lama berarti uji eksekusi/integritas lulus; tidak menghapus
catatan ketidaksesuaian lingkungan. Raw dan seluruh nilai metrik asli dipertahankan.
Keputusan pengulangan menunggu pengguna; tidak ada pengulangan otomatis.

Analisis offline baru diuji dengan **5 unit test sintetis**, termasuk batas overlap,
timezone, resource unavailable, waktu log pgbench, dan pelestarian metrik ketika
metadata ditambah. Tidak menjalankan ulang suite benchmark/dataset atau test DB.

## Persiapan pengukuran pengganti AC — otorisasi pengguna 27 Oktober 2026

Pengguna mengizinkan **hanya** backup/restore baseline_1m tiga run dan pgbench
baseline_100k tiga run diulang, charger dijaga terpasang. Workload 21 run 1M
tidak diulang karena tidak beririsan dengan gangguan. Tidak mengubah target,
workload, corpus lookup, seed42, prepare protocol, delapan client/thread,
durasi60s + warmup10s, transport tanpa TLS, atau batas timer dump/restore.
Tambahan timestamp/guard AC berada di luar interval timed. Power sampler
psutil tiap2s berjalan di host; overhead pemantau ini tidak diisolasi.

Sesi baru memakai results/bench/replacements/ac_<UTC>/ dan evidence/benchmark/
replacements/ac_<UTC>/. Sebelum promosi, salinan byte-identik evidence lama
disimpan pada evidence/benchmark/history/battery_affected_ac_<UTC>/ dengan
manifest berlabel **"terdampak baterai"**; label berlaku pada bundle sesi,
bukan klaim backup run1 lama juga pada baterai. Raw lama dipertahankan di lokasi
aslinya. Canonical backup_restore.json dan crosscheck_pgbench.json hanya
diganti bila kedua fase valid dan verifikasi AC penuh lulus. Histori audit
Kernel-Power tetap mengacu pada hasil lama melalui pointer arsip.

AC wajib terkonfirmasi pada preflight, guard tiap fase/run, dan sample2s;
setelah selesai, baca System/Kernel-Power105 untuk seluruh jendela, termasuk
event terakhir sebelum mulai. Syarat promosi: prior AC=true, semua sample
AC=true, tidak ada event AC=false, dan collector tidak gagal. Jika tidak,
pertahankan sesi sebagai gagal/tidak qualified, tanpa pengulangan otomatis
atau promosi. Power verification menyimpan batas waktu, record event dan
jumlah sample; semua sample aman juga tersedia di raw lokal.

Validasi tetap memakai checksum seluruh data/sequence 1M/100k serta checksum
sumber734. Restore ke tiga database sementara unik bench_restore_*, bukan
baseline/postgres; cleanup mengikuti utilitas lama setelah validasi lulus.
Tidak mengubah konfigurasi PG, role, container, atau Windows power plan.
Kode persiapan diuji dengan42 unit/regression test benchmark, termasuk
preservasi histori, pengalihan path, AC fail-closed, dan kedua fase tanpa
memanggil baseline_run. Hasil aktual sesi pengganti dicatat setelah selesai.

## Hasil pengukuran pengganti AC — 27 Oktober 2026

Sesi **ac_20261027T150728Z**, kode dibekukan sebelum pengukuran pada
`748fa0d71d66079244c17161f13a7dd426b80449`. Mulai **22:07:28.750794 WIB**,
selesai **22:20:39.155968 WIB**, sekitar13 menit10 detik termasuk validasi.
Backup/restore beserta validasi531,400s; fase pgbench255,208s.
**Hanya dua fase yang diotorisasi dijalankan ulang. Workload21 run tidak diulang**
karena hasil audit menunjukkan tidak terdampak gangguan baterai.

Backup/restore baseline_1m, container pg-dpr PG18, pg_dump custom plaintext,
restore ke database sementara baru dengan opsi/batas timer yang sama:

| Run | Awal backup–akhir restore WIB | Backup s | Restore s | Hasil validasi |
|---|---|---:|---:|---|
| 1 | 22:08:35.123652–22:10:06.684122 | 35.934644 | 55.625860 | 1M baris, seluruh checksum dan sequence sesuai |
| 2 | 22:11:11.972877–22:12:32.760057 | 33.390723 | 47.396286 | 1M baris, seluruh checksum dan sequence sesuai |
| 3 | 22:13:38.874611–22:14:34.855416 | 26.955186 | 29.024110 | 1M baris, seluruh checksum dan sequence sesuai |
| **Median** | | **33.390723** | **47.396286** | **3/3 lulus** |

Dump setiap run150.429.543 byte; ketiga database sementara dan dump privat
run ini sudah dihapus setelah validasi. Pemeriksaan katalog mengonfirmasi
0 database sementara milik sesi tersisa; snapshot generation tetap ada.
Baseline1M dan sumber734 cocok checksum generation; sequence tidak berubah.

Pgbench baseline_100k:8 client/thread, prepared, seed42,60s + warmup10s terpisah
per run, tanpa TLS, pool2048 key asli dan script identik hash dengan sesi lama:

| Run | Jendela proses terukur WIB | p50 ms | p95 ms | sukses/s | Error |
|---|---|---:|---:|---:|---:|
| 1 | 22:16:40.597029–22:17:40.878233 | 0.100 | 0.167 | 43932.214572 | 0 |
| 2 | 22:18:02.060135–22:19:02.278123 | 0.099 | 0.158 | 49205.763924 | 0 |
| 3 | 22:19:22.078500–22:20:22.306722 | 0.098 | 0.154 | 50908.947023 | 0 |
| **Median** | | **0.099** | **0.158** | **49205.763924** | **0** |

Mean latency median0,163ms. Baseline100k count/checksum/sequence tidak berubah;
24 raw log baru tervalidasi hash dan seluruh catatan transaksi diperiksa runner,
log sementara container dan script lookup privat sesi dibersihkan. Sample
CPU Python100k/1M pada crosscheck tetap berasal dari workload asli yang tidak
diulang, diberi scope eksplisit sebagai historis, bukan telemetry pgbench baru.

Verifikasi daya **22:07:29.007393–22:20:37.003082 WIB** mencakup seluruh tahap
timed dan validasi: **414 sample/guard, semuanya AC=true**, collector tanpa
error. Kernel-Power105 terakhir sebelum mulai: record**27381** pada
**21:56:57.699292 WIB**, AC=true; **0 event sumber daya berubah** dan
**0 event AC=false** di seluruh jendela. Pemeriksaan log juga dilakukan saat
sesi berlangsung. Hasil lengkap: power_verification.json; CSV sampling2s dan
JSON seluruh sample/guard di raw lokal. Ini bukti OS/log selama sesi, bukan
pengukuran gangguan listrik yang tidak tercatat oleh OS.

Pemilihan hasil aktif berikut menggantikan angka sekunder lama; tidak mencampur
run dari dua sesi, tidak membuang run lambat atau mengulang lagi:

| Metrik | Sesi lama, bundle "terdampak baterai" | Sesi AC pengganti, aktif |
|---|---:|---:|
| Median backup1M s | 23.389305 | **33.390723** |
| Median restore1M s | 27.942557 | **47.396286** |
| Pgbench p50 ms | 0.094 | **0.099** |
| Pgbench p95 ms | 0.142 | **0.158** |
| Pgbench sukses/s | 53661.138857 | **49205.763924** |

Angka pengganti lebih lambat; hasil3 run diterima apa adanya dengan AC terverifikasi.
Ini dua sesi berbeda, tanpa telemetry frekuensi/thermal/cache untuk mengisolasi
penyebab selisih; tidak menyimpulkan AC menyebabkan perlambatan atau baterai
mempercepat. Rasio pgbench/Python100k sekarang **26,8112x** (sebelumnya29,2389x),
tetap deskriptif dengan batas transport/driver/validasi yang dijelaskan sebelumnya.
P01–P03 protected/API tetap BELUM DIUJI; tidak memakai data ini sebagai target baru.

Ringkasan aktif: evidence/benchmark/active_measurements.json; canonical
baseline_1m/backup_restore.json, backup_restore/runs.csv dan crosscheck_pgbench.json
memuat sesi AC. summary.json/env.json diberi pointer pengganti;7 median workload
dan CSV/JSON21 run asli **tidak berubah**. session_1m_crosscheck.json mempertahankan
riwayat sesi awal dan menandai dua fase yang digantikan. Hasil lama tersimpan
byte-identik dengan manifest label **"terdampak baterai"** di
evidence/benchmark/history/battery_affected_ac_20261027T150728Z/;24 raw log pgbench
lama diperiksa ulang hash, tidak dihapus/dipindah. Reproduksi audit gangguan lama
memakai pointer arsip meski canonical sekarang telah diganti.

Evidence sesi: evidence/benchmark/replacements/ac_20261027T150728Z/.
Raw baru: results/bench/replacements/ac_20261027T150728Z/.
final_validation.json mengonfirmasi arsip,42 test sebelum pengukuran, hash raw
lama/baru, preservasi workload21/targets/ground truth,0 artefak sementara milik
sesi, checksum generation, serta verifikasi AC. Sisa disk setelah sesi sekitar
59,59GB desimal. Tidak ada retry, perubahan role/config, atau benchmark lain.

## Overnight 28 Oktober 2026: gerbang adapter belum dapat diuji

Branch run/overnight-28okt mengintegrasikan feat/verify-bench (merge 07fbf4a)
setelah izin pengguna untuk union lengkap konflik verify/NOTES.md. Migrasi
protected_1m kemudian lulus full decrypt-and-compare 1000000 baris. Run termasuk
validasi/revokasi 2525.540631 detik; sesi termasuk token/prepare/check
2540.822885 detik. AC qualified pada 2538 sampel dan 0 event AC=false.

Gerbang 2 berhenti pada prasyarat: benchmark/adapters/protected.py belum ada,
dan tidak ditemukan implementasi ProtectedAdapter di branch hasil merge.
Tersedia hanya plaintext.py dan __init__.py. Instrumentasi db_time di
diagnose_overhead.py masih berupa usulan. Oleh karena itu sampel parity
1000 kunci per skenario pada protected_100k/protected_1m belum dieksekusi,
db_time belum diukur, dan tidak ada angka ketidakcocokan atau kelulusan bisnis
yang diklaim. Evidence/benchmark/adapter_parity.json merekam
FAILED_PRECONDITION, 0 actual_parity_requests_executed, mismatches=null.

Aturan pengguna meminta STOP dan tidak retry otomatis ketika gerbang gagal.
Tidak membuat/memperbaiki adapter otomatis, tidak menjalankan benchmark B-P-P-B,
tidak mengamendemen target (langkah 3 belum dicapai), dan tidak merge ke main.
Seluruh 21 workload awal 1M, sesi pengganti backup/pgbench AC, dan ringkasan
baseline terdahulu tetap utuh. Insiden charger 00:58:21.876-00:58:54.603 WIB
terjadi sebelum migrasi 1M, saat berhenti pada merge; 0 run terdampak/diulang.
Ringkasan akhir: evidence/overnight_summary.md. Data protected_1m yang sudah
tervalidasi harus dipertahankan untuk kelanjutan setelah adapter tersedia.

## Kelanjutan 28 Oktober 2026, 10:44 WIB: berhenti pada prasyarat lingkungan

Instruksi terbaru mengizinkan merge main berisi PR #5 Alby (b8e9998), apply dan
verify TLS final dengan DPR_BASELINE_CLIENT_ADDRESS=auto, implementasi adapter,
parity, amandemen target, dan verifikasi after; benchmark B-P-P-B tetap dilarang.
Pemeriksaan awal tidak menemukan proses host Python/pgbench/pg_dump/pg_restore.
Namun docker ps dan pemeriksaan sesi DB gagal karena named pipe
dockerDesktopLinuxEngine tidak tersedia pada context desktop-linux. Proses
Docker Desktop/com.docker.backend tidak ditemukan, com.docker.service Stopped,
dan tidak ditemukan listener host pada port 5433/8200. Status proses container
dan sesi PostgreSQL tidak dapat diverifikasi; bukan diklaim nol sesi DB.

Sesuai aturan gerbang, BERHENTI tanpa start/stop layanan/container, retry,
fetch/merge main, memuat credential, apply/verify TLS, atau langkah berikutnya.
Konfigurasi final main BELUM diterapkan atau diuji pada sesi ini; hasil uji
(a)-(d) sebelumnya tidak dipakai sebagai pengganti uji ulang yang diminta.
Migrasi semalam memakai konfigurasi fix/tls-baseline-exception, dengan pengecualian
non-TLS hanya untuk bench_user/scanner_user pada kedua baseline; kesetaraan dengan
implementasi final PR #5 belum diperiksa pada sesi ini. Evidence migrasi 1M PASS
sebelumnya tetap dipertahankan, tetapi DB tidak diperiksa ulang saat engine mati.
Evidence kegagalan: evidence/overnight/resume_preflight_20261028_1044.json.
Kelanjutan dimulai dari pemeriksaan lingkungan dan langkah 1 setelah Docker
tersedia kembali serta instruksi melanjutkan; tidak mengulang migrasi yang lulus.

## Pemulihan layanan 28 Oktober 2026, 13:11 WIB

Setelah izin eksplisit pengguna, pg-dpr yang berhenti dinyalakan; service OpenBao
dari infra/compose.yaml dipastikan berjalan tanpa recreate database. OpenBao
awalnya sealed, kemudian dibuka dengan shares tersimpan di DPR_SECRETS_DIR,
tanpa mencetak shares/root/token. Transit dan ketiga key v1 lolos pemeriksaan;
HMAC sintetis menggunakan svc-app berhasil. Token svc-app dan svc-migration
lama tidak dapat dipakai, sehingga diterbitkan token baru per policy, orphan,
nonrenewable, tanpa default/root policy, TTL 14400 detik, disimpan di luar repo.

Pemeriksaan count read-only via verify-full: postgres=734, baseline_100k=100000,
baseline_1m=1000000, protected_100k=100000, protected_1m=1000000; seluruhnya PASS.
Server ssl=on dan koneksi TLS aktif pada kelima database. Ini belum menggantikan
uji ulang pengecualian baseline non-TLS (a)-(d) sesudah merge/apply final.
Evidence: evidence/overnight/recovery_20261028.json. Tidak menjalankan benchmark.
Fetch menemukan origin/main ed88ecd berisi PR #5 Alby b8e9998 dan PR #6 B 9029b77;
merge berikutnya mengikuti union dokumentasi dan STOP konflik kode/konfigurasi.

## TLS final diterapkan; STOP prasyarat db_time, 28 Oktober 2026

Merge origin/main ed88ecd (PR #5 b8e9998 dan PR #6) ke run/overnight-28okt
selesai tanpa konflik pada 0ba90db. Setelah membaca implementasi final,
enable_tls apply lalu verify dijalankan dengan credential bench/scanner DPAPI
existing dan DPR_BASELINE_CLIENT_ADDRESS=auto. Keduanya PASS, alamat teramati
172.17.0.1/32. Tidak ada restart postmaster; ID container dan OID DB tetap.

Uji nyata (a)-(d) PASS: bench_user/scanner_user ke kedua baseline tanpa TLS;
role lain ke baseline tanpa TLS ditolak; app_user ke protected_100k/protected_1m
tanpa TLS ditolak; app_user verify-full ke kedua protected berhasil. Protected_734
belum dibuat sehingga connection_matrix_complete global tetap false; ini bukan
klaim login app ke protected_734 sudah diuji. Evidence apply/verify dan matrix
khusus (a)-(d) ada di evidence/overnight/tls_final_20261028/; laporan TLS lama
dipertahankan sebagai previous.json, canonical infra/postgres-tls.json diperbarui.

Konfigurasi final diterapkan sekarang. Migrasi semalam memakai konfigurasi
fix-branch yang setara dalam mempertahankan kondisi baseline non-TLS untuk
bench/scanner serta mewajibkan TLS pada protected. Perbedaan final yang disengaja:
pengecualian hostnossl (sebelumnya host) mempertahankan precedence metode auth
koneksi terenkripsi; deteksi alamat tetap melalui login verify-full. Tidak
mengklaim kedua berkas konfigurasi identik byte demi byte.

Pada prasyarat langkah 2 ditemukan shared_preload_libraries kosong, konteks
parameter postmaster, compute_query_id=auto. Paket pg_stat_statements versi 1.12
tersedia tetapi extension/view tidak terpasang pada kedua baseline dan kedua
protected. Karena itu db_time dari pg_stat_statements belum dapat diukur.
Dokumentasi PostgreSQL 18 menyatakan preload membutuhkan restart server:
https://www.postgresql.org/docs/18/pgstatstatements.html . CREATE EXTENSION saja
tidak mengaktifkan preload. Statistik mencakup semua database; kelak view dapat
dipasang di database monitoring tanpa mengubah skema baseline. Aktivasi akan
mengubah konfigurasi dibanding sesi baseline awal dan harus dicatat eksplisit.

Sesuai aturan gerbang terbaru, BERHENTI pada prasyarat ini, tanpa restart,
ALTER SYSTEM, CREATE EXTENSION, retry otomatis, implementasi adapter/parity,
amandemen target, verifikasi after, atau benchmark B-P-P-B. db_time=null berarti
NOT_MEASURED, bukan nol atau hasil EXPLAIN pengganti yang dilabel ulang.
Evidence: evidence/overnight/db_time_preflight_20261028.json. Kelanjutan menunggu
instruksi penyiapan pg_stat_statements dan pelanjutan langkah 2; seluruh hasil
migrasi dan dataset yang sudah lulus dipertahankan.

## pg_stat_statements dan adapter protected, 28 Oktober 2026

Pengguna secara eksplisit menyetujui preload dan restart pg-dpr. Sebelum restart
tidak ditemukan proses host Python/pgbench/pg_dump/pg_restore atau sesi DB client.
Nilai shared_preload_libraries lama kosong; updater mempertahankan daftar lama
bila ada dan menambahkan pg_stat_statements. ALTER SYSTEM, satu restart pg-dpr,
readiness, lalu CREATE EXTENSION IF NOT EXISTS pada kedua baseline dan kedua
protected berhasil. Tidak restart OpenBao. Count kelima DB tetap tepat; OpenBao
tetap unsealed; TLS apply/verify dan uji nyata (a)-(d) kembali PASS. Protected_734
belum tersedia, tetap pending. Evidence: overnight/pg_stat_statements_20261028/.

pg_stat_statements aktif mulai persiapan sesi B-P-P-B. Baseline awal 100k/1M
diukur TANPA extension/preload ini; hanya B versus P dalam blok B-P-P-B dengan
konfigurasi sekarang yang boleh dibandingkan langsung. Hasil baseline awal
dipertahankan sebagai sesi historis dan tidak diulang. Instalasi extension
adalah perubahan skema eksplisit yang diizinkan pengguna; isi anggota tidak
diubah. Tidak menambah membership pg_read_all_stats atau grant monitoring pada
bench_user/app_user. Atribut role dan membership diperiksa tetap sama.

DbTimeMonitor memakai koneksi admin/monitoring verify-full terpisah, memfilter
dbid/userid/toplevel tanpa mengekspor teks SQL. Delta total_exec_time/calls
diambil hanya pada jendela terukur, di luar waktu request; reset/deallocation
atau counter menurun membuat pengukuran gagal. Dilaporkan mean per request
bisnis dan per SQL call; bukan p50/p95 server yang tidak disediakan counter.
db_time tidak mencakup planning, transport, validasi Python atau kripto.
Runner menerima monitor opsional; jalur baseline historis tidak ditimpa.
Compare menilai selisih absolut baca 5ms/tulis 10ms berdampingan dengan rasio
1.5x, throughput 70%, error tidak naik, tanpa mengganti kegagalan rasio menjadi
kelulusan melalui ambang absolut. Mixed memakai batas tulis dan dicatat.

ProtectedAdapter memakai app_user verify-full + principal UUID RLS, exact lookup
HMAC toolkit A, legacy_row_id sebagai locator dan anggota_id UUID untuk AAD.
Profil tunggal membuka seluruh 29 kolom sama dengan plain; list hanya nama dan
REF jenis_kelamin plus legacy id, batch unwrap hanya PII. KeyManager tanpa cache
antarrequest (TTL/max_entries=0), satu client/manager per koneksi worker, tidak
berbagi lock Transit antarworker. Update/insert tetap force_rollback; insert
SELECT setelah trigger creator scope, tanpa bypass RLS. Fail closed tanpa nilai
atau credential di error/evidence. Korpus benchmark privat asli tidak diubah.

Test baru adapter memakai fixture buatan sendiri dan AES-GCM nyata, memeriksa
domain minimal, UUID AAD, fail closed, endpoint/identity, rollback, penghitung
db_time, comparison, dan cleanup principal. Suite gabungan awal 76 PASS/1 FAIL
karena unit test metadata lama membaca charger fisik. Test itu diisolasi dengan
power_plugged sintetis (tidak mengubah guard runtime), lalu suite 77 PASS.
Kedua JUnit disimpan di results/overnight-28okt/; bukan retry gerbang parity DB.

Gerbang parity menggunakan 1000 profil berbeda dari korpus lookup yang sama dan
1000 anchor halaman berbeda seed42 khusus parity (korpus benchmark tetap 64
halaman). Setup admin membuat principal/scope sementara hanya pada protected;
workload selalu app_user dan scope dihapus saat selesai. Audit setup/cleanup
tercatat, bukan dihapus; tidak mengubah data anggota. Ini pemeriksaan kebenaran
terbatas, bukan pengukuran performa atau benchmark B-P-P-B.
