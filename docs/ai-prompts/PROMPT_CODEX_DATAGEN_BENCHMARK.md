# Tugas: Generator Data Sintetis + Benchmark Baseline (Hackathon DPR RI 2026)

## Konteks
Repo ini berisi solusi Pelindungan Data Pribadi untuk dump anggota DPR (data sintetis). Database baseline (plaintext, kondisi "before") ada di PostgreSQL 18, container `pg-dpr`, `127.0.0.1:5433`, tabel `public.anggota` (734 baris, kolom `id` identity PK + 29 kolom dari dump). Schema ada di `sql/baseline/01_schema.sql`. Soal lomba mewajibkan perbandingan sistem **sebelum vs sesudah** proteksi dengan **dataset, perangkat, dan beban kerja yang sama**, data diperbesar secara sintetis, minimal 3 kali pengulangan, laporan median, p50/p95, throughput, error rate, CPU, RAM, ukuran storage, waktu backup/restore, dan **hasil mentah disimpan**. Acuan metodologi: buku Onno W. Purbo *Data Leak-Proof* Bab 8 (eksperimen berpasangan).

Taruh kode di `datagen/` dan `benchmark/`. Jangan ubah `scanner/` dan folder aplikasi web. Untuk `Makefile`, `README.md`, `.gitignore`: hanya tambah, jangan hapus isi yang ada. Platform pengembang: Windows + PowerShell (tanpa `make` bawaan), jadi sediakan juga skrip `.ps1` atau perintah `python -m ...` yang setara. Python 3.11+, dependensi dipin di `requirements.txt` masing-masing folder (psycopg v3, Faker bila perlu, numpy opsional, psutil).

## Aturan keamanan
- Kredensial hanya dari env var: `DATAGEN_DATABASE_URL` (role pemilik schema baseline) dan `BENCH_DATABASE_URL` (role untuk benchmark). Tidak ada password di kode, log, atau output. Sediakan `.env.example` berisi placeholder.
- Query berparameter. Jangan mencetak nilai baris ke log.
- Data harus **100% sintetis**. Jangan memakai nama orang sungguhan atau daftar nama publik.
- Hasil benchmark ditulis ke `results/bench/...` (sudah di-.gitignore).

## Bagian A: `datagen` (generator data)
`python -m datagen --rows 100000 --seed 42 --target-db baseline_100k`

1. Membuat database baru (mis. `baseline_100k`, `baseline_1m`) di server yang sama, menerapkan `sql/baseline/01_schema.sql`, lalu mengisi data. Database baseline asli (`postgres`, 734 baris) **tidak boleh diubah**.
2. **734 baris asli ikut dimasukkan** (dibaca dari tabel `postgres.public.anggota` sumber), lalu ditambah baris sintetis sampai jumlah target.
3. **Deterministik**: seed yang sama menghasilkan data identik. Catat seed, jumlah baris, versi generator, dan checksum ringkas di `results/bench/datasets/<db>.json`.
4. Meniru **distribusi** dump (hitung otomatis dari 734 baris sumber, jangan hardcode): proporsi jenis_kelamin, tempat_lahir, pekerjaan_terakhir, status_kawin, agama, nama_bank, nama_kppn, distribusi jumlah_anak, rentang tanggal_lahir.
5. Meniru **format**: no_ktp 14 digit berawalan nol, rekening 16 digit, npwp 15 digit, nip_kppn 18 digit, handphone 10 digit prefiks 08x, telpon_jakarta 11 digit prefiks 021, telpon_daerah 10 digit, alamat `Jl. Contoh No. N, <Kota>`, ruangan `DUMMY-<n>` unik.
6. Kolom yang unik di sumber tetap **unik** (no_ktp, rekening, npwp, nip_kppn, handphone, telpon_daerah, email, pengguna, ruangan). Gunakan pembangkitan berbasis urutan + permutasi agar tidak ada tabrakan.
7. Meniru **relasi antar kolom** yang ada di sumber, secara sengaja (ini sifat sistem "before" yang akan dilindungi): nama acak berbentuk huruf/tanda baca acak seperti sumber (bukan nama asli); nama_lengkap = nama_tanpa_gelar = nama; nama_rekening = 20 karakter pertama nama; email = nama dinormalisasi + nomor urut + `@example.com`; pengguna = `dummy_` + nama dinormalisasi + nomor urut; kota alamat_daerah = tempat_lahir; jumlah_jiwa = jumlah_tanggungan + 1; status K iff tanggal_pernikahan terisi, dan tanggungan = anak + 1 untuk K.
8. Anomali sumber (kode_bank tidak cocok dengan nama_bank; tanggal_pernikahan sebelum usia 17) dikendalikan oleh flag `--replicate-anomalies` (default: ikuti proporsi sumber). Catat pilihan di metadata.
9. Insert cepat dengan `COPY` dalam batch. Setelah selesai jalankan `ANALYZE` dan buat indeks yang sama dengan schema.
10. Validasi otomatis setelah generate: jumlah baris, keunikan, format, dan relasi di atas; simpan hasil validasi ke metadata. Gagal = exit code non-nol.
11. Sediakan juga `python -m datagen snapshot --db baseline_100k --out <path>` yang menjalankan `pg_dump -Fc` (via `docker exec` atau `pg_dump` lokal) untuk snapshot baseline, tanpa menaruh password di command line (gunakan env `PGPASSWORD` dari environment yang sudah diset, atau `.pgpass` di luar repo).

## Bagian B: `benchmark`
`python -m benchmark run --db baseline_100k --label before --scenario all --runs 3 --duration 60 --concurrency 8 --warmup 10`

1. **Workload bisnis** (definisikan di `benchmark/workloads.yaml`, harus bisa dipakai ulang persis sama untuk sistem "after"):
   - `read_by_nik`: cari 1 anggota berdasarkan no_ktp (exact match)
   - `read_by_email`: cari berdasarkan email
   - `read_profile`: ambil profil lengkap berdasarkan id
   - `list_page`: daftar 50 anggota (pagination by id)
   - `update_contact`: ubah handphone 1 anggota
   - `insert_member`: tambah 1 anggota sintetis
   - `mixed`: campuran 70% baca / 30% tulis
   Parameter kueri (NIK/email/id yang dicari) diambil dari **daftar kunci tetap** yang dibuat sekali dengan seed dan disimpan di `results/bench/keys/<db>.json`, supaya before dan after mencari kunci yang sama. Operasi tulis dibungkus transaksi yang di-ROLLBACK atau memakai kunci khusus agar dataset tidak berubah antar run.
2. Implementasi workload diletakkan di modul adapter (`benchmark/adapters/plaintext.py`) dengan antarmuka yang jelas, sehingga nanti cukup menambah `adapters/protected.py` (pencarian via blind index + dekripsi di aplikasi) tanpa mengubah runner.
3. Runner: thread/async worker sejumlah `--concurrency`, durasi tetap, warmup tidak dihitung. Catat **setiap request** (timestamp, scenario, latency_ms, ok/error) ke CSV mentah.
4. Metrik sistem selama run (`benchmark/collect_metrics`): CPU dan RAM container `pg-dpr` (via `docker stats --no-stream` berkala) dan proses client (psutil), ukuran database (`pg_database_size`), ukuran tabel + indeks. Simpan CSV mentah.
5. Ringkasan per run dan per scenario: p50, p95, p99, mean, throughput (req/s), error rate. Ringkasan gabungan 3 run memakai **median antar-run**. Simpan `summary.json` dan `summary.csv`.
6. Metadata lingkungan di `env.json`: OS, CPU, RAM, versi PostgreSQL, versi Python, nama DB, jumlah baris, seed, parameter run, git commit hash. Tanpa password.
7. Perintah `python -m benchmark backup-restore --db baseline_100k --label before --runs 3`: ukur waktu `pg_dump -Fc` dan `pg_restore` ke database sementara, ukuran file dump, dan verifikasi jumlah baris setelah restore. File dump sementara dihapus setelah diukur kecuali `--keep`.
8. Perintah `python -m benchmark compare --before results/bench/before --after results/bench/after --out results/bench/compare`: tabel perbandingan + persentase perubahan, dan grafik PNG (matplotlib) p50/p95/throughput per scenario. (Untuk sekarang cukup berjalan dengan data before saja, bagian after menyusul.)
9. **Target kinerja** dibaca dari `docs/targets.md` atau `benchmark/targets.yaml` jika ada, dan hasil compare menandai lulus/gagal. Jangan membuat atau mengubah nilai target; bila file belum ada, tampilkan peringatan.

## Test
- Unit test generator: determinisme (seed sama = hash sama), keunikan, format, relasi (pakai jumlah kecil, mis. 2.000 baris, di DB uji jika `DATAGEN_TEST_DATABASE_URL` ada; selain itu test fungsi murni).
- Unit test perhitungan persentil dan median antar-run.
- Test bahwa tidak ada nilai baris yang tercetak ke log/output ringkasan.

## Definisi selesai
- `baseline_100k` terbentuk, validasi lulus, snapshot dibuat.
- `benchmark run ... --label before --runs 3` menghasilkan CSV mentah, `summary.json`, `env.json` untuk semua scenario.
- `benchmark backup-restore --label before` menghasilkan waktu backup/restore dan ukuran.
- README berisi bagian "Data sintetis" dan "Benchmark" dengan perintah PowerShell yang persis.
- Tulis ringkasan keputusan, asumsi, dan keterbatasan di `benchmark/NOTES.md`.
