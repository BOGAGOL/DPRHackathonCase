# Tugas: Bangun Scanner Data Pribadi (Tantangan 1, Hackathon DPR RI 2026)

## Konteks singkat
Kami tim finalis Hackathon DPR RI 2026 bertema Pelindungan Data Pribadi (UU No. 27 Tahun 2022). Studi kasus: dump database anggota DPR (data sintetis) yang sudah kami import ke PostgreSQL 18 (container Docker `pg-dpr`, host `127.0.0.1`, port `5433`, database `postgres`, tabel `public.anggota`, 734 baris, 30 kolom termasuk `id` PK yang kami tambahkan). Rujukan metodologi: buku Onno W. Purbo, *Data Leak-Proof: Teknik Proteksi Data di PostgreSQL* (Bab 2.4 inventaris, 2.6 scanner hanya menemukan kandidat, 2.7 prioritas P0-P3, 3.1 matriks keputusan).

Soal lomba menuntut: "Kembangkan teknik analisis dump berdasarkan struktur, nama kolom, isi data, teks bebas, dan hubungan antar tabel. **Jangan hanya mengikuti komentar SQL atau nama tabel.** Uji ketepatan deteksi terhadap klasifikasi acuan." Hasil AI/otomatis wajib diverifikasi manusia, jadi scanner ini **semi-otomatis**: menemukan kandidat dan memberi skor, manusia meninjau kolom yang meragukan.

## Langkah pertama
1. Periksa struktur folder repo ini dulu. Letakkan semua kode scanner di `scanner/` (buat jika belum ada), test di `scanner/tests/`, contoh konfigurasi di `scanner/config/`. Jangan mengubah folder lain kecuali menambah target di `Makefile` (buat jika belum ada) dan satu bagian di `README.md`.
2. Baca file `AGENTS.md` jika ada dan patuhi.
3. Jika ada asumsi yang tidak pasti, tulis di `scanner/NOTES.md`, jangan diam-diam memutuskan.

## Teknologi
- Python 3.11+. Dependensi minimal: `psycopg[binary]` (v3), `PyYAML`, `jinja2` (untuk laporan HTML), `pytest`. Hindari pandas kecuali benar-benar perlu. Tulis `scanner/requirements.txt` dengan versi dipin.
- CLI dengan `argparse`. Satu entry point: `python -m scanner ...`.

## Aturan keamanan (WAJIB)
- Kredensial **hanya** dari environment variable `SCANNER_DATABASE_URL` (contoh di `scanner/.env.example` berisi placeholder, tanpa password asli). Jangan pernah menulis password di kode, test, log, atau output. Pastikan `.env` ada di `.gitignore`.
- Scanner hanya **membaca**. Sediakan `scanner/sql/scanner_role.sql` yang membuat role `scanner_user` dengan `LOGIN`, `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOINHERIT`, hanya `CONNECT` + `USAGE` schema + `SELECT` tabel target, tanpa hak tulis. Password role diisi lewat variabel psql (`:'scanner_password'`), bukan ditulis di file. Set `default_transaction_read_only = on` untuk role ini.
- Semua query memakai parameter atau `psycopg.sql.Identifier` untuk nama tabel/kolom. Tidak boleh string formatting untuk SQL.
- **Output tidak boleh memuat nilai lengkap data pribadi.** Semua contoh nilai harus dimasking (lihat fungsi masking di bawah). Pesan error dan log juga tidak boleh mencetak nilai baris.
- Sampel dibaca dengan `TABLESAMPLE` atau `ORDER BY random() LIMIT n` (default n=1000, bisa diatur), tidak menarik seluruh tabel besar ke memori.

## Mode input
1. **Mode database**: `python -m scanner db --schema public --sample 1000 --out results/scanner/<label>/`
2. **Mode file dump**: `python -m scanner dump --file path/ke/dump.sql --out ...` membaca file SQL plain (`INSERT INTO ... VALUES (...)`, gaya MySQL dengan backtick maupun gaya PostgreSQL / `COPY ... FROM stdin`). Mode ini penting: scanner yang sama akan dijalankan pada `pg_dump` **sebelum** dan **sesudah** proteksi untuk membuktikan apa yang masih terbaca jika dump bocor. Juga sediakan mode `files` yang memindai teks bebas pada file log/CSV/backup untuk pola NIK, email, telepon, rekening (output: file, baris, jenis, nilai termasking).
3. `--label before|after|<bebas>` dicatat di output bersama timestamp, versi scanner, dan info sumber (host/db atau path file, **tanpa** password).

## Sinyal per kolom (hitung semuanya, simpan sebagai fitur)
Pisahkan dua skor:
- **content_score** (0-100) dari isi data:
  - pola regex per jenis (persentase sampel yang cocok), untuk: email, telepon seluler/rumah Indonesia, NIK, NPWP, rekening/nomor kartu, tanggal, kode pos, alamat (kata kunci "Jl.", "No.", "RT", "RW", "Kel.", "Kec."), nama orang (heuristik), dll.
  - bentuk nilai: persentase digit, panjang tetap vs bervariasi, karakter set, awalan nol
  - **bukti negatif**: misal panjang tidak sesuai jenis, distribusi digit, atau konteks yang bertentangan mengurangi skor. Contoh nyata di data kami: regex NIK 16 digit cocok 0% di `no_ktp` (NIK di dump ini 14 digit) tetapi 100% di `rekening`. Scanner tidak boleh menyimpulkan `rekening` adalah NIK hanya dari regex.
  - kardinalitas: rasio nilai unik / baris (identifier vs kategori), rasio NULL
  - kamus nilai: agama, bank, jenis kelamin, status kawin, kota
  - teks bebas: deteksi PII yang terselip di dalam kalimat
- **name_score** (0-100) dari nama kolom (kamus kata kunci Indonesia dan Inggris: nik, ktp, npwp, rek, rekening, hp, telp, phone, email, alamat, address, lahir, birth, agama, religion, nama, name, ibu, anak, sakit, diagnosa, dll.). Nama kolom adalah **sinyal pendukung**, bukan penentu.

Aturan keputusan:
- `confidence` = gabungan berbobot, dengan bobot isi lebih besar daripada nama (konfigurasi di `scanner/config/weights.yaml`).
- **auto_accept hanya jika content_score memenuhi ambang** (mis. >= 60) dan confidence >= 80. Kolom dengan name_score tinggi tapi content_score rendah harus masuk `needs_review`, bukan auto_accept.
- `needs_review` untuk confidence menengah atau sinyal bertentangan.
- Confidence rendah **bukan** berarti "bukan data pribadi". Label tetap `low_confidence` dan tetap tercantum di laporan (tidak dibuang).

## Analisis antar kolom (wajib)
1. **Kolom turunan / duplikat**: setelah normalisasi (lowercase, buang spasi dan tanda baca, buang angka di akhir), cek apakah nilai kolom A sama dengan, merupakan prefiks dari, atau terkandung di kolom B, dan pada berapa persen baris. Laporkan pasangan dengan persentase tinggi (mis. >= 90%) sebagai `derived_from`. Di data kami diharapkan terdeteksi: `nama_lengkap` dan `nama_tanpa_gelar` identik dengan `nama`; `nama_rekening` adalah prefiks `nama`; `email` dan `pengguna` mengandung `nama`. Implikasi yang harus dicatat: melindungi `nama` saja tidak cukup.
2. **Ketergantungan fungsional / aritmetika sederhana**: cek apakah kolom A dapat dihitung dari kolom B (mis. `jumlah_jiwa = jumlah_tanggungan + 1`), atau bagian teks kolom A sama dengan kolom B (mis. kota di `alamat_daerah` sama dengan `tempat_lahir`), atau kolom A terisi jika dan hanya jika kolom B bernilai tertentu (mis. `tanggal_pernikahan` terisi iff `status_kawin = 'K'`). Implementasikan secara umum (bukan hardcode nama kolom ini), lalu pastikan contoh-contoh itu tertangkap.
3. **Quasi-identifier dan k-anonymity**: untuk kombinasi 1 sampai 3 kolom dari kandidat quasi-identifier (kolom berkardinalitas rendah-menengah seperti tanggal lahir, tempat lahir, jenis kelamin, agama, pekerjaan, kota), hitung berapa baris yang unik (k=1) dan k minimum. Laporkan kombinasi paling berbahaya. Pada data penuh kami, `tempat_lahir + tanggal_lahir + jenis_kelamin` unik untuk 730 dari 734 baris; scanner harus menemukan ini sendiri. Batasi jumlah kombinasi agar tetap cepat. Ini dijalankan pada seluruh tabel (agregat `GROUP BY` di database), bukan sampel, dan outputnya hanya angka agregat tanpa nilai.
4. **Relasi antar tabel**: baca foreign key dari `information_schema` jika ada. Jika tidak ada FK, deteksi kandidat join berdasarkan nilai yang sama antar kolom di tabel berbeda. (Saat ini baru satu tabel, tapi kode harus siap untuk banyak tabel.)

## Klasifikasi dan rekomendasi
Untuk setiap kolom, output:
- `detected_type` (nik, nama, email, telepon, alamat, tanggal_lahir, tempat_lahir, agama, status_perkawinan, keluarga, rekening, npwp, identifier_lain, kategori, operasional, tidak_diketahui)
- `pdp_class`: `umum`, `spesifik`, atau `non_pribadi` sesuai UU PDP Pasal 4 (spesifik: kesehatan, biometrik, genetika, catatan kejahatan, data anak, keuangan pribadi; agama termasuk **umum** menurut Pasal 4(3) tetapi tandai `sensitivity_note: rawan diskriminasi`)
- `risk_level`: rendah/sedang/tinggi/kritis
- **Prioritas P0-P3 sesuai Bab 2.7 buku**: skor = sensitivitas + volume + keterpaparan + kemudahan eksploitasi + dampak + kelemahan pemulihan (masing-masing 1-5, total 6-30; P0 25-30, P1 19-24, P2 13-18, P3 6-12). Scanner menghitung **sensitivitas** dan **kemudahan eksploitasi** dari isi data. Empat faktor lain (volume, keterpaparan, dampak, kelemahan pemulihan) dibaca dari `scanner/config/environment_<label>.yaml` karena bergantung pada kondisi sistem (before vs after). Simpan nilai tiap faktor di output agar bisa diaudit.
- `recommendation`: salah satu `delete`, `retain`, `hash`, `encrypt`, `tokenize`, `mask` (boleh kombinasi, mis. `encrypt+blind_index+mask`), mengikuti urutan keputusan Bab 3.1: pertanyaan pertama selalu "perlu disimpan atau tidak?". Kolom duplikat/turunan didorong ke `delete` atau minimisasi. Password selalu `hash` (Argon2id), tidak pernah `encrypt`.
- `reason`: kalimat yang dirangkai otomatis dari sinyal yang terpicu (mis. "100% digit; panjang tetap 14; unik per baris; nama kolom mengandung 'ktp'"). Ini memenuhi syarat "dasar penilaian".
- `triage`: `auto_accept`, `needs_review`, `low_confidence`
- `sample_masked`: 1-3 contoh termasking

## Fungsi masking (dipakai di semua output)
Ikuti format contoh panitia: nama `On*** Pu***`, NIK `3174********1234` (untuk panjang lain: 4 depan + bintang + 4 belakang), telepon `0812****7890`, email `on***@example.com`, rekening `************4567`. Untuk nilai yang tidak dikenal: tampilkan panjang dan tipe karakter saja, mis. `<14 digit>`. Tulis unit test untuk setiap format.

## Output
Di folder `--out`:
1. `inventory.csv` dengan kolom persis:
   `table,column,data_type,detected_type,pdp_class,risk_level,priority,priority_score,f_sensitivity,f_volume,f_exposure,f_exploitability,f_impact,f_recovery,content_score,name_score,confidence,triage,derived_from,sample_masked,reason,recommendation,allowed_roles,search_need`
   (`allowed_roles` dan `search_need` boleh diisi default dari config dan direvisi manusia.)
2. `relations.json`: kolom turunan, ketergantungan, kandidat join.
3. `k_anonymity.json`: kombinasi quasi-identifier dan jumlah baris unik.
4. `run_meta.json`: label, waktu, versi, sumber, ukuran sampel, durasi.
5. `report.html`: satu file statis (tanpa JS eksternal) berisi tabel inventaris berwarna per prioritas, daftar `needs_review`, temuan relasi, k-anonymity. Tidak memuat nilai lengkap.

## Evaluasi terhadap ground truth
`python -m scanner evaluate --pred results/.../inventory.csv --truth scanner/ground_truth.csv --out results/.../evaluation.json`
- `ground_truth.csv` dibuat manual oleh anggota tim (jangan buat isinya, cukup sediakan `scanner/ground_truth.template.csv` dengan header `table,column,is_personal,detected_type,pdp_class,risk_level,notes`).
- Hitung precision, recall, F1 untuk `is_personal`; akurasi `detected_type` dan `pdp_class`; confusion matrix; daftar false positive/negative.
- Evaluasi dilakukan pada **output mentah scanner sebelum tinjauan manusia**.
- Sediakan juga mode `--baseline regex_only` yang hanya memakai regex sederhana, supaya kami bisa membandingkan "regex saja" vs "metode gabungan".

## Test wajib (pytest, `scanner/tests/`)
1. Unit test masking, regex, normalisasi, skor.
2. **Uji nama kolom disamarkan**: buat fixture dari data sintetis kecil (buat sendiri dengan Faker atau generator sederhana, JANGAN menyalin data dump) dengan struktur mirip tabel anggota, lalu ganti semua nama kolom menjadi `col_01`, `col_02`, dst. Scanner harus tetap mendeteksi email, telepon, NIK-like identifier, rekening, tanggal, alamat dengan confidence wajar, dan kolom turunan tetap terdeteksi. Ini bukti bahwa deteksi tidak hanya ikut nama kolom.
3. **Uji regex menipu**: kolom berisi 16 digit yang bukan NIK (mis. rekening dengan konteks bank) tidak boleh auto_accept sebagai NIK.
4. **Uji output tidak bocor**: jalankan scanner pada fixture, lalu pastikan tidak ada satu pun nilai asli lengkap dari fixture yang muncul di file output mana pun.
5. Uji mode dump: parse dump gaya MySQL (backtick) dan gaya PostgreSQL.
6. Uji k-anonymity pada fixture kecil dengan jawaban yang diketahui.
Test berbasis database boleh memakai database sementara jika `SCANNER_TEST_DATABASE_URL` diset, dan di-skip jika tidak.

## Makefile dan README
Tambahkan target:
- `make scanner-install`
- `make scan LABEL=before` (mode db)
- `make scan-dump FILE=... LABEL=...`
- `make scan-eval LABEL=before`
- `make scanner-test`
Tambahkan bagian "Scanner" di `README.md`: tujuan, cara membuat `scanner_user`, cara menjalankan, arti setiap kolom output, keterbatasan.

## Larangan
- Jangan hardcode nama kolom tabel `anggota` di logika deteksi (kecuali di kamus nama yang generik dan di test yang memang memverifikasi kasus ini).
- Jangan memakai layanan eksternal / LLM API untuk klasifikasi.
- Jangan menulis atau mengubah data di database.
- Jangan commit file hasil scan dari data asli ke repo (tambahkan `results/` ke `.gitignore` kecuali README di dalamnya).

## Definisi selesai
- `make scanner-test` lulus.
- `make scan LABEL=before` pada database `pg-dpr` menghasilkan kelima file output.
- Temuan berikut muncul tanpa hardcode: duplikat kolom nama, `email`/`pengguna`/`nama_rekening` turunan dari `nama`, `jumlah_jiwa = jumlah_tanggungan + 1`, kota `alamat_daerah` = `tempat_lahir`, ketergantungan `tanggal_pernikahan` dengan `status_kawin`, kombinasi `tempat_lahir + tanggal_lahir + jenis_kelamin` dengan 730/734 baris unik, `no_ktp` terdeteksi sebagai identifier walau bukan 16 digit, `rekening` tidak salah dilabeli NIK.
- Di akhir, tulis ringkasan di `scanner/NOTES.md`: apa yang dibuat, keputusan desain, asumsi, keterbatasan, dan saran langkah berikutnya.
