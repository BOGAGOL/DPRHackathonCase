# 2. Analisis masalah, data dan prioritas perlindungan

## Masalah dan tujuan yang tepat

Database menyimpan profil anggota yang dibutuhkan layanan sah. Salinan plaintext
membawa nilai informasi meskipun penyerang tidak memiliki login aplikasi. Solusi
bertujuan mengurangi informasi yang pulih dari salinan tersebut, menjaga fungsi
layanan, mengukur biaya proteksi dan menyediakan pemulihan. Solusi tidak menjanjikan
pencegahan setiap kebocoran atau tahan kompromi aplikasi sekaligus key-plane.

Studi kasus sintetis panitia tidak memberi dasar untuk menyimpulkan karakter semua
database DPR RI yang nyata. Istilah “anggota” menunjuk model dataset, bukan identitas
orang nyata atau bukti proyek digunakan operasional oleh DPR RI.

## Identitas tim dan kontribusi

Alby: infra/PKI/OpenBao, toolkit, profile, migrasi, SQL role/RLS, backup/restore dan
rotasi. Zhafif: backend/frontend, auth, scope/DTO, query analis, deployment dan
operasional aplikasi. Delf: scanner, datagen, benchmark, simulasi leakage, residual,
evidence dan analisis eksperimen. Penulisan laporan dan validasi akhir tanggung
jawab tim, bukan pengesahan otomatis oleh agen AI.

## Fakta sumber dan adaptasi PostgreSQL

- Input nyata terdiri dari 734 INSERT ke satu tabel, 29 atribut eksplisit, tanpa
  CREATE TABLE/PK/FK/trigger. Jangan menyebut banyak tabel/relasi FK yang ditemukan
  hanya karena latar soal generik menggambarkan organisasi besar.
- Tim menambahkan DDL PostgreSQL 18, menyesuaikan quoting MySQL dan mempertahankan
  string identifier/nol awal, NULL serta hubungan data. `id` baseline adalah
  surrogate buatan tim, bukan atribut ke-30 panitia.
- Sumber `postgres.public.anggota` dipertahankan. Target terpisah
  `protected_734`, `protected_100k`, `protected_1m`; semua uji skala harus menyebut
  asal/lingkungan. Jangan menulis target 1M hanya uji disposable: migrasi 1M nyata
  pada laptop benchmark kini punya all-rows validation tersendiri.
- `no_ktp` sumber 14 digit, bukan NIK nasional 16 digit yang tervalidasi.
  Rekening 16, NPWP 15, nip_kppn 18 digit; semua perlu perlakuan string.
- 367 tanggal pernikahan NULL; 42 tanggal perkawinan sebelum lahir dan 131 usia
  perkawinan di bawah 17 menurut observasi sumber. Ini anomali data sintetis,
  dipertahankan/dilaporkan, bukan diperbaiki diam-diam.
- Tiga kolom nama identik pada seluruh 734 baris. Nama rekening/email/pengguna
  berasal dari nama/nomor ruang; tempat lahir terkait kota alamat daerah;
  jumlah_jiwa = jumlah_tanggungan + 1. Dependensi membantu inferensi penyerang.
- Regex NIK 16 digit saja salah sasaran: 0 cocok pada no_ktp 14 digit, tetapi dapat
  cocok pada rekening. Kebutuhan isi+struktur+semantik terlihat konkret di sini.

## Pembesaran data yang reproducible

`datagen/` versi 1.0.0 membentuk baseline_100k = 734 sumber + 99.266 sintetis dan
baseline_1m = 734 sumber + 999.266 sintetis, seed 42, total tepat sesuai target.
Sumber dibaca, bukan ditimpa. Evaluasi memisahkan source_734/synthetic/all,
menjaga kolom/NULL/nol awal sumber, keunikan identifier global, keterkaitan dan
proporsi anomali tambahan. Snapshot/known-values/corpus privat tidak ikut laporan.

Reproduksi identik mengandaikan sumber, versi generator, seed, parameter, urutan
dan algoritme yang sama; jangan menjanjikan seluruh ciphertext identik antarlaptop.
UUIDv4, DEK dan nonce sengaja acak. Kesetaraan isi setelah decrypt yang penting.

## Assessment yang mengendalikan profile

Scanner gabungan mengevaluasi nama, pola isi, kamus, statistik/keunikan, tipe,
teks bebas dan dependensi. Evidence berupa inventory CSV/report HTML dengan pola
termasking, alasan, priority dan triage; tidak mengekspor nilai anggota lengkap.
Keterkaitan intra-tabel yang ditemukan bukan bukti scanner menemukan FK pada dump
yang tidak memiliki DDL. Ruang generalisasi masih terbatas.

`scanner/ground_truth_eval.csv` memiliki 29 label sumber; ada file 30 label dengan
surrogate id untuk konteks, tetapi evaluator utama mengecualikan id. Label map
menyelaraskan taksonomi evaluasi dan prediksi. Evaluasi raw v1.2 in-sample:
TP26/FP1/FN0/TN2, precision 96,2963%, recall 100%, F1 98,1132%. Satu false positive
kode_bank tidak disembunyikan; keputusan kripto tetap boleh melindunginya karena
risiko proxy, walaupun acuan jenis nilainya non-pribadi.

Policy dibangun dari inventory yang dicatat dalam provenance, lalu override tim.
Profile saat ini 29 kolom: **21 PII + 4 FIN = 25 AEAD**, **4 REF**, tiga bidx dan
age_band turunan. Ini bukti “Assessment-Driven Protection Profile”: assessment
→ keputusan kebutuhan akses/search/risiko → mesin migrasi/verifikasi. Bukan AI
langsung mengubah skema atau memutuskan kelas hukum tanpa review.

## Tiga klasifikasi yang tidak boleh dicampur

1. **Kelas PDP**: umum/spesifik/non-pribadi menurut konvensi acuan dan UU PDP.
2. **Risiko/prioritas**: exposure/uniqueness/impact dan kebutuhan layanan; skor
   scanner adalah triage awal, bukan residual risiko produksi yang terukur.
3. **Domain/kontrol teknis**: PII/FIN/REF, AEAD/bidx/masking/agregasi; tidak identik
   satu-ke-satu dengan kategori hukum.

Agama masuk umum tetapi berisiko profil tinggi. jumlah_anak adalah jumlah, bukan
data identitas anak tertentu; Dokter adalah pekerjaan, bukan riwayat kesehatan.
Acauan memberi rekening kategori spesifik; nama_rekening umum sebagai nama meski
domain teknis FIN. Metadata institusi non-pribadi sebagai jenis nilai tidak membuat
baris yang terhubung ke individu aman dipublikasikan. `nip_kppn` ambigu pemiliknya.
Klasifikasi merupakan review awal, bukan pernyataan hukum final/sertifikasi patuh.

## Prioritas dan alasan pilihan

| Urutan | Keputusan | Alasan dan tradeoff |
|---|---|---|
| P0 | Pisahkan rahasia, TLS/least privilege dan lindungi identifier/keuangan | Menghilangkan pembacaan langsung dari dump protected dan akses layanan yang terlalu luas |
| P0 | AEAD/AAD per field dan DEK per record/domain | Integritas, anti-swap, domain blast radius; menambah ukuran/RPC/latensi |
| P1 | Bidx hanya no_ktp/email/pengguna | Exact lookup perlu indeks; tidak membuat indeks tambahan seluruh field; equality/dictionary tetap bocor |
| P1 | kode_bank FIN, bukan REF | Hampir unik sendiri; kombinasi plaintext awal dapat unik 734/734 |
| P1 | REF4 + age_band dan A5 aggregate-only | Fungsi statistik minimum; tetap perlu pengukuran residual dan suppression |
| P1 | Validasi seluruh migrasi, backup integritas dan drill | Proteksi tidak boleh merusak fungsi/data/pemulihan |
| P2 | Rotasi wrapper, monitoring, kustodian/DR | Membatasi operasi kunci; butuh operator dan custody yang benar |
| Terbuka | Minimisasi tiga nama, DP/aggregate filtering, HA/DR lintas mesin | Rekomendasi; kontrak tidak menghapus kolom, teknik belum diklaim diterapkan |

Jangan menafsirkan tahap sebagai seluruhnya selesai di semua VM. Matriks per kolom
berikutnya berada di tabel 29 kolom pada bab 11 dan `tables/column-matrix.csv`.
