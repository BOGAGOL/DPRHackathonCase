# PROJECT CONTEXT: Final Hackathon DPR RI 2026 (BACA PERTAMA)

Dokumen ini adalah konteks utama proyek. Agen AI dan anggota tim WAJIB membaca dokumen ini lebih dulu,
lalu `docs/contracts/CONTRACT.md` (aturan teknis yang mengikat), `docs/TEAM_PLAN.md` (pembagian dan
jadwal), lalu prompt modul masing-masing di `docs/ai-prompts/`.

Urutan prioritas jika ada pertentangan:
1. Soal final resmi dan dokumen Detail Hackathon (panitia)
2. `docs/contracts/CONTRACT.md`
3. Dokumen ini
4. `docs/TEAM_PLAN.md` dan prompt modul
5. Dokumen lain (termasuk arsip `docs/legacy-md_zhafif/`, yang BUKAN acuan)

---

## 1. Lomba dan tim

- Lomba: **Final Hackathon DPR RI 2026**, tema "Keamanan Data dan Informasi".
- Judul soal: **"Database Bocor: Seberapa Jauh Data Pribadi Tetap Terlindungi?"**
- Studi kasus dokumen detail: "Transformasi Database MySQL Berisi Data Pribadi Menjadi Sistem Data yang
  Aman, Terukur, dan Tetap Berkinerja Baik".
- Penyelenggara/juri terkait penulis buku **Onno W. Purbo**: *Data Leak-Proof: Teknik Proteksi Data di
  PostgreSQL agar Kebocoran Tidak Berarti Apa-Apa* (2026) dan *Overview Serangan ke Data dan Database*
  (2026). Istilah dan artefak buku dipakai di laporan agar mudah dikenali juri, tetapi solusi harus
  MENGEMBANGKAN buku, bukan menyalin.
- Tim (3 orang, repo `BOGAGOL/juara1onno`, private):
  - **Alby**: Modul A (infra, OpenBao, crypto toolkit, protection profile, migrasi, role DB, backup/restore).
  - **Zhafif**: Modul B (Service Application dan access control).
  - **Delf**: Modul C (scanner, datagen, benchmark, verifikasi, leakage budget, evidence, SBOM, koordinasi laporan).

## 2. Inti masalah

Sebuah database menyimpan profil anggota Dewan (identitas, alamat, kontak, rekening, keluarga, dll).
Pertanyaannya: jika salinan database (dump, backup, file data) jatuh ke pihak tidak berwenang, apakah data
pribadi langsung terbaca, dan apakah aplikasi tetap melayani pengguna sah?

Sasaran solusi kita BUKAN "mencegah database bocor", melainkan:
> Membuat salinan data yang bocor kehilangan nilai bagi pihak tidak berwenang, mengukur secara jujur apa
> yang masih bisa diketahui penyerang, sambil menjaga layanan tetap berfungsi, berkinerja, dan dapat dipulihkan.

Tema dibatasi pada threat modeling, identifikasi data pribadi, rekonstruksi identitas, inferensi, dan
mitigasi. BUKAN eksploitasi server atau serangan jaringan. Hanya data sintetis.

## 3. Enam tantangan soal (kerangka seluruh pekerjaan dan laporan)

1. **Temukan data yang harus dilindungi**: analisis dump berdasarkan struktur, nama kolom, isi, teks bebas,
   relasi (jangan hanya ikut nama kolom). Inventaris + klasifikasi UU PDP + risiko + rekomendasi + siapa
   boleh akses. Uji ketepatan deteksi terhadap klasifikasi acuan (ground truth).
2. **Kurangi nilai data ketika bocor**: minimisasi, enkripsi terautentikasi, tokenisasi, pseudonimisasi,
   masking, pembatasan akses. Simulasi kebocoran: apa yang terbaca, terlindungi, dan masih bisa
   disimpulkan dari metadata/pola. Bedakan bocor tanpa kunci vs data + kunci ikut bocor.
3. **Tiga kondisi data**: at rest, in transit, in use. Jelaskan batas setiap kontrol.
4. **Lindungi backend dan frontend**: autentikasi, otorisasi peran dan per record, query berparameter,
   validasi input, least privilege, rahasia, audit; frontend hanya menerima data yang diizinkan.
   "Data yang disembunyikan pada tampilan tetapi tetap dikirim ke browser belum terlindungi."
5. **Buktikan keamanan dan kinerja**: before vs after dengan dataset, perangkat, beban kerja sama;
   data diperbesar sintetis; p50/p95, throughput, error, CPU, RAM, storage, waktu backup/restore;
   target ditetapkan SEBELUM pengujian; minimal 3 kali; median; simpan hasil mentah; pengguna sah tetap
   benar, akses terlarang ditolak, backup dapat dipulihkan.
6. **Panduan penerapan bertahap**: prasyarat, inventarisasi, prioritas, implementasi, migrasi, validasi,
   rollback, operasional, pemulihan, biaya/sumber daya, risiko tersisa.

## 4. Persyaratan wajib tambahan (dokumen Detail Hackathon)

- Inventaris: lokasi, contoh pola tanpa nilai lengkap, jenis, klasifikasi (umum/spesifik/non-pribadi),
  risiko (rendah/sedang/tinggi/kritis), dasar penilaian, rekomendasi (encrypt/mask/tokenize/hash/retain/delete).
- Matriks perlindungan berdasarkan kegunaan data (tidak wajib enkripsi semua kolom). Password = hashing
  adaptif (Argon2id), bukan enkripsi.
- Manajemen kunci: tidak di kode/repo/dump/dokumentasi; terpisah dari data; mekanisme akses; rotasi;
  pemulihan; dampak hilang/bocor; pemisahan peran DBA vs pengelola kunci.
- Dump/backup: tidak terbaca tanpa kunci; skrip backup dan restore; cek integritas; bukti restore;
  retensi dan pemusnahan; password/kunci tidak masuk shell history, log, repo.
- Role minimal: `app_user`, `analyst_user` (hanya data termasking/pseudonim), `auditor_user`,
  `backup_user`, `admin_user`.
- Format masking contoh: Nama `On*** Pu***`, NIK `3174********1234`, Telepon `0812****7890`,
  Email `on***@example.com`, Rekening `************4567`. Masking bukan enkripsi.
- Periksa data pribadi di: general/slow/error query log, log aplikasi, file sementara, riwayat perintah,
  hasil ekspor, dokumentasi, tangkapan layar.
- Uji wajib: dump tidak terbaca tanpa kunci; analis tidak melihat nilai asli; app_user hanya sesuai fungsi;
  pencurian file data DB tidak langsung membuka isi; kunci tidak ada di dump/repo; backup yang diubah gagal
  integritas; data terhapus tidak muncul di backup baru.
- Lisensi: dokumentasi CC BY-NC 4.0; kode MIT/Apache-2.0/GPL-3.0; dataset milik panitia, tidak boleh
  dipublikasikan; komponen pihak ketiga ikut lisensi asal.
- Istilah hukum: "Pelindungan Data Pribadi" (UU No. 27 Tahun 2022). Spesifik = kesehatan, biometrik,
  genetika, catatan kejahatan, data anak, keuangan pribadi. Agama termasuk UMUM (Pasal 4(3)) walau
  berisiko tinggi.

## 5. Luaran, jadwal, penilaian

**Dikumpulkan (satu folder Google Drive, via Google Form panitia):**
1. Laporan/panduan teknis PDF (gaya tesis, 40-70 halaman): analisis, rancangan, prioritas, langkah
   implementasi, hasil pengujian, keterbatasan, referensi.
2. Slide presentasi (PDF/Google Slides). File yang dikirim = file yang dipresentasikan (berubah = gugur).
3. Lampiran reproduksi: kode, konfigurasi tanpa rahasia aktif, README, skrip pengujian, hasil mentah.

15 luaran rinci panitia: repo, README, laporan, inventaris + klasifikasi, matriks risiko, diagram arsitektur,
threat model, skrip migrasi, skrip backup/restore, skrip benchmark, hasil benchmark before/after, bukti uji
akses, daftar keterbatasan, SBOM, presentasi.

**Jadwal:** submit Kamis 29 Okt 2026 paling lambat 23.59 WIB (target internal sebelum 18.00).
Presentasi 31 Okt 2026, maks 15 menit termasuk demo + 10 menit tanya jawab (siapkan inti 5 menit).

**Kriteria penilaian:** ketepatan analisis, mutu inovasi, alasan prioritas, efektivitas kontrol, kualitas
bukti pengujian, kinerja layanan, kejelasan panduan dan presentasi. **Klaim tanpa bukti tidak dinilai.**
Juri diminta tidak terpukau jargon tanpa solusi yang berjalan dan tidak menuntut produk siap operasi.

## 6. Dataset (fakta terverifikasi)

- `anggota_dummy.sql`: hanya 734 `INSERT` ke satu tabel `anggota`, 29 kolom, tanpa CREATE TABLE, PK, FK,
  trigger. Escape kutip `''` kompatibel PostgreSQL; adaptasi cukup menghapus backtick + DDL buatan tim
  (`sql/baseline/`). Validasi import: 734 baris, NIK unik 734, NIK 14 digit utuh, 367 menikah = 367 tanggal.
- Nama acak (karakter teracak). `nama` = `nama_lengkap` = `nama_tanpa_gelar` (734/734).
- Kolom turunan nama: `nama_rekening` (20 karakter pertama), `email`, `pengguna` (734/734).
- Ketergantungan: kota `alamat_daerah` = `tempat_lahir`; `jumlah_jiwa` = `jumlah_tanggungan` + 1;
  `tanggal_pernikahan` terisi iff `status_kawin` = K; nomor di email/pengguna = nomor `ruangan`.
- Format: `no_ktp` 14 digit (bukan NIK 16), `rekening` 16, `npwp` 15, `nip_kppn` 18, semua berawalan nol.
  Regex NIK 16 digit cocok 0 di `no_ktp` tapi 734 di `rekening` (regex saja menipu).
- Anomali: `kode_bank` tidak konsisten dengan `nama_bank` (ratusan kode per bank); 42 tanggal pernikahan
  sebelum tanggal lahir; 131 menikah sebelum usia 17; kelahiran hingga 2005.
- Re-identifikasi: `tempat_lahir + tanggal_lahir + jenis_kelamin` unik untuk 730/734; `tanggal_lahir`
  saja unik ~700.
- Temuan penting: kolom yang awalnya dianggap aman dibiarkan plaintext (`jenis_kelamin`,
  `pekerjaan_terakhir`, `nama_kppn`, `nama_bank`, `kode_bank`) bersama-sama unik untuk 734/734;
  `kode_bank` saja unik 373. Karena itu `kode_bank` dimasukkan domain FIN (dienkripsi).
- Ground truth independen (Alby): `scanner/ground_truth.csv` + metodologi; 29 kolom (26 pribadi, 3 non-pribadi:
  `nama_kppn`, `nama_bank`, `kode_bank` sebagai nilai institusi); label memakai taksonomi sendiri
  (PERSON_NAME, NATIONAL_ID, ...) sehingga evaluator butuh label map.

## 7. Keputusan arsitektur (final)

- **Engine:** PostgreSQL 18 (diizinkan soal). Benchmark keamanan = PostgreSQL plaintext vs PostgreSQL
  protected (jangan campur dengan efek MySQL -> PostgreSQL).
- **Key plane:** OpenBao (fork open-source Vault, dipakai buku) dengan Transit; TLS; token per policy,
  tanpa root token di aplikasi.
- **Enkripsi:** application-level AEAD AES-256-GCM, nonce acak 12 byte, AAD mengikat ciphertext ke
  tabel|kolom|anggota_id|versi (cegah tukar ciphertext antar record/kolom). Gagal dekripsi = fail closed.
- **Envelope per record:** DEK_PII dan DEK_FIN per anggota, disimpan wrapped oleh `pii-kek` dan
  `finance-kek` di OpenBao. Blast radius: bocornya satu domain tidak membuka domain lain.
- **Blind index (HMAC):** hanya `no_ktp`, `email`, `pengguna` (exact lookup). Kebocoran kesetaraan/frekuensi
  diukur dan diakui.
- **Plaintext tersisa (REF):** `jenis_kelamin`, `pekerjaan_terakhir`, `nama_kppn`, `nama_bank` + turunan
  `age_band`; diuji k-anonymity.
- **Tidak ada kolom yang dihapus.** Nama tidak di-hash. Minimisasi (3 kolom nama identik) hanya rekomendasi.
- **Migrasi:** ke database BARU (`protected_734`, `protected_100k`), idempoten, decrypt-and-compare.
- **Akses:** 5 role panitia + `schema_owner`, `migration_user`, `scanner_user`; RLS sebagai lapisan
  tambahan (bukan pengganti otorisasi backend); peran aplikasi operator, privileged_officer,
  finance_officer, analyst, auditor, anggota (hanya data sendiri).
- **Backup:** pg_dump di-stream langsung ke enkripsi (tanpa file plaintext sementara), manifest + HMAC,
  restore 2 mode (tanpa kunci: tetap ciphertext; dengan kunci: layanan pulih), tamper test, retention test.
- **Toolkit keamanan** (scanner, migrasi, verifikasi) terpisah dari Service App, CLI, berjalan lokal.
  Dashboard opsional dan read-only.
- Rincian teknis mengikat: lihat `docs/contracts/CONTRACT.md`.

## 8. Tiga inovasi yang dibawakan (di luar buku Onno)

1. **Assessment-Driven Protection Profile**: scanner berbasis isi (bukan nama kolom), mendeteksi kolom
   turunan, ketergantungan, k-anonymity, diukur precision/recall terhadap ground truth independen;
   hasilnya menjadi `policy/protection_profile.yaml` yang mengendalikan migrasi dan verifikasi.
2. **Leak it on purpose + Leakage Budget**: simulasi bocor terhadap artefak nyata, metrik ESCE (exact
   sensitive cell exposure), DIE (direct identifier exposure), ELS (equality leakage surface), DBR
   (decryption blast radius), plus k-anonymity sisa before vs after (termasuk temuan `kode_bank`).
3. **Cryptographic blast-radius separation**: domain PII vs finance; demo "kunci finance bocor, identitas
   tetap terlindungi".
Tambahan: perbaikan celah kode referensi buku (OpenBao client memakai `context` bukan AAD + token statis;
backup.sh meninggalkan file plaintext; TLS dimatikan di quick-start; integrasi belum pernah diuji).

## 9. Batas jujur (wajib disampaikan)

- Jika aplikasi dan kemampuan dekripsi dikuasai bersamaan, kerahasiaan tidak lagi dijamin; nilai desain
  adalah membatasi blast radius, deteksi (audit), revokasi, rotasi.
- Blind index membocorkan kesetaraan dan frekuensi.
- Kolom REF dan pola NULL tetap terlihat.
- RLS berbasis session variable tidak melindungi dari pencuri kredensial app_user.
- Backup lama dapat masih memuat data yang sudah dihapus hingga masa retensi habis.
- Hasil scanner bersifat in-sample pada satu tabel.

## 10. Bukti (evidence) dan laporan

- Semua hasil mesin ke `evidence/<kategori>/` (JSON/CSV), tanpa data pribadi plaintext. Laporan dan slide
  hanya mengambil angka dari evidence.
- Setiap klaim laporan diberi status: Diimplementasikan + Diuji / Diimplementasikan / Rencana, dengan
  ID evidence dan perintah reproduksi.
- Kerangka laporan: Ringkasan; Pendahuluan; Landasan teori; Analisis kondisi awal + threat model;
  Bab T1-T6 (satu bab per tantangan); Keterbatasan; Kesimpulan; Pustaka; Lampiran (indeks evidence,
  reproduksi, SBOM, ground truth, runbook, pernyataan penggunaan AI, lisensi).
- `docs/targets.md` ditulis dan di-commit SEBELUM benchmark (hash commit dicatat sebagai bukti).

## 11. Aturan kerja

- Ikuti `AGENTS.md`. Satu modul = satu branch = satu sesi agen AI. Merge ke main lewat PR dengan review
  anggota lain (bukti verifikasi hasil AI).
- Jangan menjalankan migrasi terhadap `baseline_100k` sebelum Modul C mengonfirmasi baseline benchmark
  terekam. Code freeze Rabu 28 Okt 20.00.
- Database `postgres` (734 baris asli) tidak boleh diubah. Dataset panitia dan `sql/baseline/02_data.sql`
  tidak di-commit. Repo tetap private.
- Platform tim: Windows + PowerShell; Docker Desktop; PostgreSQL di container `pg-dpr` port 5433.

## 12. Glosarium singkat

- **AEAD**: enkripsi terautentikasi dengan associated data (AES-GCM): rahasia + segel integritas + konteks.
- **AAD**: label konteks yang tidak dienkripsi tetapi ikut diverifikasi saat dekripsi.
- **DEK / KEK**: kunci data / kunci yang membungkus DEK. **Envelope encryption**: DEK dibungkus KEK.
- **OpenBao Transit**: layanan kripto; kunci tidak pernah keluar dari OpenBao.
- **Blind index**: HMAC berkunci dari nilai ternormalisasi untuk pencarian exact tanpa plaintext.
- **k-anonymity**: setiap kombinasi atribut dimiliki minimal k orang; k=1 berarti unik (dapat dikenali).
- **ESCE/DIE/ELS/DBR**: metrik Leakage Budget (lihat bagian 8).
- **Fail closed**: jika verifikasi/dekripsi gagal, sistem menolak, tidak menampilkan data cadangan.
