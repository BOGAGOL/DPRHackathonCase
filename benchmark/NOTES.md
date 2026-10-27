# Modul C — baseline awal level DB, langkah 3

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
