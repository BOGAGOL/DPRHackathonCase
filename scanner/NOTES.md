# Catatan implementasi scanner

## Lingkup dan status awal (sebelum langkah 4)

Implementasi ada seluruhnya di `scanner/`, selain target Makefile dan bagian
Scanner pada README. `.gitignore` yang sudah ada mengabaikan `.env`, environment
Python, dan `results/*` dengan pengecualian `results/README.md`; tidak perlu diubah.
Tidak ada AGENTS.md di repositori atau direktori induk yang diperiksa.
Tidak ada data panitia yang disalin sebagai fixture, ground truth yang dikarang,
atau hasil scan asli yang ditambahkan ke Git.

Status historis sebelum langkah 4 (26 Oktober): scanner v1.1 belum dijalankan ulang pada database asli. Hasil run pertama
v1.0 di `results/scanner/before_v1/` sudah dibaca, khususnya inventory.csv dan
relations.json, untuk menyusun perbaikan. Angka k-anonymity satu kolom juga
diperiksa dari JSON hasil tersebut. SCANNER_DATABASE_URL tidak tersedia di sesi
ini; pengguna menjalankan validasi database sendiri. Tidak ada upaya mengubah,
menjalankan container, atau menulis data pada database asli. Hasil run pertama
dipertahankan untuk pembandingan; nilai termasking tidak dipakai sebagai input
pengganti nilai asli untuk mengklaim scan baru.

## Yang dibuat dan keputusan desain

- CLI tunggal `python -m scanner`, mode db, dump, files, evaluate.
- Python 3.11+, psycopg 3, PyYAML, Jinja2, pytest dengan versi langsung dipin.
  Dependensi diinstal dalam `scanner/.venv` untuk pengujian lokal.
- PostgreSQL memakai satu snapshot REPEATABLE READ READ ONLY, timeout query
  120 detik, query terparameter, dan Identifier untuk semua nama sumber. SELECT
  sampel memakai ORDER BY random() LIMIT; memori dibatasi per tabel. Jumlah tabel
  dan kolom tetap memengaruhi total memori. Scan tidak menjalankan skrip role.
- Parser SQL streaming tidak mengeksekusi input. Reservoir sampling bersifat
  deterministik untuk dump; pembacaan database acak. Seluruh dump disimpan pada
  SQLite sementara untuk GROUP BY penuh, kemudian file dihapus, termasuk ketika
  parse gagal. Disk sementara harus dipercaya; penghapusan bukan secure erase.
- Fitur agregat lengkap disimpan di features.json: kecocokan regex dan kamus,
  teks bebas, panjang, digit, karakter, nol awal, entropi digit, keunikan, NULL,
  seluruh skor per jenis dan nama, serta bukti negatif. Tidak ada nilai baris di
  fitur. Kardinalitas dan rasio NULL adalah estimasi sampel.
- Confidence default 0.8 isi + 0.2 nama. Auto_accept membutuhkan isi >=60 dan
  confidence >=80; sinyal nama saja masuk needs_review. Nama disamarkan tidak
  menggagalkan deteksi isi, tetapi kandidat ambigu dapat tetap needs_review.
  Name_score di CSV adalah skor nama **untuk jenis terpilih**; bukti nama jenis
  lain tetap tersedia pada fitur dan reason.
- Regex 16 digit tidak membuktikan NIK. Struktur wilayah/tanggal dan keragaman
  digit diperiksa sebagai bukti plausibilitas, bukan validasi kependudukan.
  Konteks bank menurunkan dugaan NIK; nama rekening memberi bukti yang bertentangan.
  NIK panjang nonstandar memerlukan nama pendukung, seluruh nilai digit, panjang
  tetap, dan unik per baris; tetap needs_review dengan catatan panjang tidak baku.
  Tanpa nama pendukung, identifier nonstandar tetap identifier_lain. Konteks
  bank pada tabel adalah heuristik lemah dan dapat memengaruhi identifier lain;
  tinjau kandidat 16 digit secara manual.
- Duplikat/prefix/containment dinormalisasi tanpa tanda baca/spasi dan angka
  terminal pada teks (angka murni tetap dipertahankan). Paling sedikit tiga
  nilai bervariasi dan rasio 90% dibutuhkan. Sumber nama diprioritaskan atas
  email/username, dan nama kolom paling ringkas dipakai sebagai sumber kanonik
  untuk duplikat. Ini heuristik arah relasi, bukan bukti kausal. Masking kategori
  pada ketergantungan iff tidak mengekspor nilai kategori mentah.
- Ketergantungan aritmetika mencari offset konstan; dependency fungsional
  mencari konsistensi kelompok, serta hubungan kehadiran iff sebuah kategori.
  Sumber dengan rasio unik non-NULL >0.9 dikecualikan dari functional dan dicatat
  sekali di near_unique_quasi_identifiers; nama daftar ini bukan jaminan bahwa
  seluruh anggotanya hanya quasi-identifier (direct ID juga bisa hampir unik).
  Hasil berdasarkan sampel, tidak membuktikan aturan berlaku pada semua baris.
- Quasi-identifier dipilih dari bukti tanggal, kota, gender, agama, perkawinan
  dan kardinalitas rendah-menengah. Default maksimal 12 kandidat dan 300
  kombinasi ukuran 1–3 per tabel. Agregat memakai semua baris di database/dump,
  bukan sampel. Pengelompokan NULL mengikuti SQL; hanya jumlah keluar. JSON
  menyimpan semua agregat, diurutkan ukuran kombinasi lalu jumlah baris unik
  menurun. HTML menampilkan maksimal 15 kombinasi minimal, menyembunyikan
  superset pada tabel sama jika subset sudah memiliki >=95% baris unik.
- FK dibaca dari information_schema; join kandidat ditaksir dari irisan nilai
  sampel, termasuk identifier angka. Maksimal 500 pasangan join diperiksa.
  FK komposit mempertahankan urutan posisi. Jika information_schema menyembunyikan
  FK dari role SELECT-only, pembacaan metadata beralih ke pg_catalog dengan
  pemeriksaan has_table_privilege. Kandidat join tetap dilaporkan.
- Kelas spesifik dan umum mengikuti Pasal 4 UU PDP; agama umum dengan
  sensitivity_note rawan diskriminasi di fitur dan reason. Referensi resmi:
  https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022.
- Prioritas persis P0 25–30, P1 19–24, P2 13–18, P3 6–12. Sensitivitas dan impact
  per jenis berasal dari impact.yaml; exploitability dari bukti isi (kategori,
  operasional, dan hitungan keluarga bernilai 1). Volume, exposure, recovery
  dari environment. Semua wajib integer 1–5 dan diaudit di CSV/metadata.
  Berkas environment lama dengan impact masih diterima, tetapi nilainya
  diabaikan dan migrasi dicatat dalam legacy_environment_impact_ignored.
  Contoh before/after adalah **asumsi**, bukan bukti efektivitas kontrol.
- Rekomendasi dimulai dari tinjauan kebutuhan penyimpanan. `retention` di
  weights.yaml dapat memetakan nama kolom ke `delete` atau `retain`; tanpa
  keputusan tetap diusulkan proteksi sambil meninjau retensi. retain berarti
  masih perlu disimpan, bukan otomatis boleh plaintext. Duplikat/turunan memakai
  review_minimization dan consistent_protection_with untuk meninjau kebutuhan
  serta konsistensi proteksi, tanpa keputusan penghapusan otomatis. Password
  tetap hash Argon2id, termasuk saat isi tidak dikenali atau mempunyai turunan.
  Nama publik default retain+mask_for_analyst karena hash rentan kamus. Tanggal
  lahir memakai generalize_for_analyst dan reason mencatat jumlah baris unik
  (k=1) dari agregat satu kolom seluruh sumber, bukan rasio unik sampel. Bila
  pengukuran tidak tersedia (misalnya files), ketidaktersediaan dicatat eksplisit.
  Scanner hanya menyarankan tindakan; tidak menerapkan penghapusan/enkripsi/hash.
- Output CSV menambahkan consistent_protection_with ke header v1.0. Ada fitur audit JSON. Laporan
  statis memakai autoescape, CSP, dan tanpa JS/dependensi eksternal. Error CLI
  tidak menampilkan DSN, SQL driver, nilai baris, ataupun traceback.
- Mode files membaca baris teks UTF-8 dan mencari embedded regex. Sampel teks
  inventaris dan temuan masing-masing dibatasi --sample per file; total temuan
  tetap dihitung dan dicatat. Output findings.csv memuat lokasi dan mask, bukan
  baris asli. Direktori output dikecualikan dari pemindaian direktori input.
- Baseline regex_only membandingkan classifier regex sederhana tanpa bobot nama,
  konteks, dan validasi semantik NIK; analisis relasi tetap tersedia terpisah.
- Evaluasi memakai pdp_class != non_pribadi sebagai kandidat personal, termasuk
  low_confidence. Missing prediction dihitung negatif (dan salah untuk akurasi
  jenis/kelas). Baris tanpa label acuan dilaporkan, bukan diasumsikan benar.
  Gunakan output mentah yang belum diedit; scanner tidak dapat membuktikan CSV
  yang diberikan pengguna belum direvisi manusia.

## Asumsi dan keterbatasan yang perlu dikonfirmasi

1. Naskah lengkap Bab 2.7/3.1 buku tidak tersedia di repo. Rentang prioritas,
   enam faktor, dan urutan retensi mengikuti spesifikasi prompt, bukan klaim
   bahwa implementasi mereproduksi seluruh matriks buku.
2. Tanggal tanpa nama semantik masih diwakili kandidat tanggal_lahir bila konteks
   lain tidak tersedia. Versi 1.1 menambahkan jenis tanggal_pernikahan dari nama
   dan/atau hubungan kehadiran tanggal dengan kategori perkawinan. Pola NULL
   bersyarat memperkuat bukti, namun tidak membuktikan konteks pernikahan sendiri.
   Verifikasikan apakah tanggal tersebut lahir, pernikahan, atau operasional.
   Gender memakai detected_type kategori, tetap pdp_class umum.
3. Angka panjang sulit dibedakan antara rekening, NIK, dan ID ketika seluruh
   konteks hilang; pengujian menuntut confidence wajar dan kandidat untuk ditinjau,
   bukan kepastian identitas. Nama orang/kota/agama/kesehatan memakai heuristik
   serta kamus kecil yang perlu dikembangkan dari temuan yang sudah diverifikasi.
   Sinyal biometrik/genetika/kejahatan/anak terutama berbasis nama; kebutuhan
   review tetap ada ketika isi tidak cukup jelas. Keluarga tidak selalu data anak.
4. Parser mendukung CREATE TABLE biasa, INSERT literal multirow dengan kolom
   opsional, identifier backtick/double quote, string apostrof ganda/escape
   backslash, NULL, angka desimal, dan COPY FROM stdin format teks/tab.
   E-string dasar didukung; cast/ekspresi SQL, dollar-quoted literal, INSERT SELECT, COPY CSV,
   format biner/custom archive tidak didukung. Gunakan pg_dump plain default
   (COPY teks) atau literal INSERT sederhana. Input tidak didukung gagal dengan
   pesan aman. FK dump belum diparse; gunakan mode db untuk metadata FK resmi.
5. ORDER BY random() tidak menarik seluruh tabel ke RAM klien, tetapi dapat
   mahal di server. Banyak tabel/kolom dan GROUP BY 300 kombinasi bisa mahal;
   kurangi batas di weights.yaml untuk database besar. Pemilihan kandidat memakai
   sampel sehingga kombinasi penting di luar kandidat dapat terlewat.
6. DDL yang tak dibutuhkan untuk inventaris (ALTER/COMMENT/GRANT/dll.) diabaikan;
   parser tidak merekonstruksi schema migration atau menjalankan fungsi.
7. Path file, nama tabel/kolom, host, dan nama database adalah metadata sumber
   yang ditampilkan sesuai spesifikasi. Pastikan metadata sendiri tidak memuat
   rahasia. Nama domain email dipertahankan dalam format mask yang diminta.
8. Jalankan scanner pada storage lokal yang terkontrol; hasil fitur/relasi dan
   sampel termasking masih berpotensi sensitif walaupun tanpa nilai lengkap.

## Validasi database asli: perintah persis di PowerShell

Jalankan dari root repo. GNU Make opsional; padanan Python selalu disertakan.
Tidak perlu mengirim password ke chat.

```powershell
Set-Location C:\dev\juara1onno
python -m venv scanner/.venv
.\scanner\.venv\Scripts\Activate.ps1
python -m pip install -r scanner/requirements.txt
python -m pytest scanner/tests -q

# Jika masih berhenti, pengguna menyalakan container asli sendiri:
docker start pg-dpr
docker port pg-dpr
```

Pastikan port yang ditampilkan benar-benar 5433; jika berbeda sesuaikan variabel
port di bawah. Administrator menjalankan provisioning **sekali** (skrip CREATE
ROLE akan gagal bila role sudah ada, tanpa mengubah role lama):

```powershell
psql -X -W -h 127.0.0.1 -p 5433 -U postgres -d postgres -f scanner/sql/scanner_role.sql
```

Password admin diminta psql. Password role scanner diminta Python `getpass`
melalui command substitution psql (stdout ditangkap ke variabel, tidak dicetak
ke terminal), kemudian dimasukkan ke CREATE ROLE lewat `:'scanner_password'`.
Prompt menolak fallback yang menampilkan input. Provisioning ini
adalah operasi administrator terpisah dari scanner; scanner sendiri hanya
membaca kredensial koneksi dari SCANNER_DATABASE_URL. Dokumentasi psql:
https://www.postgresql.org/docs/18/app-psql.html.
Jangan gunakan `-v
scanner_password=...` berisi rahasia nyata di riwayat terminal. Pastikan audit
hak PUBLIC oleh administrator: PostgreSQL tidak mendukung DENY per role; hak
TEMP database, CREATE schema, SELECT/INSERT/UPDATE/DELETE/TRUNCATE tabel atau
SECURITY DEFINER routines yang diberikan ke PUBLIC diwariskan walau NOINHERIT.
Skrip provisioning tidak mencabut hak PUBLIC secara global karena dapat
memengaruhi aplikasi lain. Jika ada hak tidak aman, administrator harus
memperbaiki hak PUBLIC dan memberi ulang hak aplikasi terkait sebelum memakai
role dalam produksi. Default read-only dan transaksi scanner adalah lapisan
tambahan, bukan pengganti pembatasan hak.

Atur URL dari prompt agar password tidak tertulis pada command atau file:

```powershell
$scannerCredential = Get-Credential -UserName scanner_user -Message 'Kredensial role baca-saja scanner'
$scannerUser = [Uri]::EscapeDataString($scannerCredential.UserName)
$scannerSecret = [Uri]::EscapeDataString($scannerCredential.GetNetworkCredential().Password)
$env:SCANNER_DATABASE_URL = 'postgresql://' + $scannerUser + ':' + $scannerSecret + '@127.0.0.1:5433/postgres'
Remove-Variable scannerSecret, scannerUser, scannerCredential

# Memastikan sesi benar-benar read-only, tanpa query tulis:
$env:SCANNER_TEST_DATABASE_URL = $env:SCANNER_DATABASE_URL
python -m pytest scanner/tests/test_database.py -q

# Perintah utama; menghasilkan lima file wajib dan features.json:
python -m scanner db --schema public --sample 1000 --label before --out results/scanner/before
# Jika GNU Make tersedia, padanannya:
# make scan LABEL=before

Get-ChildItem results/scanner/before
Import-Csv results/scanner/before/inventory.csv | Select-Object column,detected_type,content_score,name_score,confidence,triage,derived_from,recommendation | Format-Table -AutoSize
Get-Content results/scanner/before/relations.json
$scannerK = Get-Content results/scanner/before/k_anonymity.json -Raw | ConvertFrom-Json
$scannerK | Where-Object { ($_.columns | Sort-Object) -join ',' -eq 'jenis_kelamin,tanggal_lahir,tempat_lahir' } | Format-List
Start-Process (Resolve-Path results/scanner/before/report.html)
```

Kriteria penerimaan pada data asli:

- Jumlah baris total 734 tercatat di run_meta.json; sampel default mencakup semua
  734 karena lebih kecil daripada limit 1000.
- derived_from menangkap nama_lengkap/nama_tanpa_gelar/nama_rekening/email/pengguna
  dari nama; alamat_daerah mengandung tempat_lahir.
- dependencies menangkap offset jumlah_jiwa = jumlah_tanggungan + 1 dan
  presence_iff_category antara status_kawin dan tanggal_pernikahan.
- no_ktp menjadi nik dengan catatan panjang tidak baku bila bukti isi terpenuhi;
  rekening bukan NIK. Nama rendah kardinalitas menjadi kategori; jumlah keluarga
  bukan data anak individual. ID integer berurutan adalah kandidat operasional.
- Kombinasi tempat_lahir + tanggal_lahir + jenis_kelamin memiliki total_rows=734
  dan unique_rows=730. Bila tidak muncul, cek kualitas data, pemilihan kandidat,
  batas kombinasi dan hubungan jumlah baris. Jangan mengubah angka hasil scanner
  agar cocok dengan angka acuan.

Bandingkan baseline pada snapshot/sumber sama dan direktori terpisah:

```powershell
python -m scanner db --schema public --sample 1000 --label before --baseline regex_only --out results/scanner/before-regex

# File ini harus diisi manual oleh anggota tim, bukan oleh scanner:
Copy-Item scanner/ground_truth.template.csv scanner/ground_truth.csv
# Edit scanner/ground_truth.csv, kemudian evaluasi hasil mentah:
python -m scanner evaluate --pred results/scanner/before/inventory.csv --truth scanner/ground_truth.csv --out results/scanner/before/evaluation.json
python -m scanner evaluate --pred results/scanner/before-regex/inventory.csv --truth scanner/ground_truth.csv --out results/scanner/before-regex/evaluation.json
```

Untuk dump before/after yang sudah disiapkan tim:

```powershell
python -m scanner dump --file results/dumps/before.sql --label before --out results/scanner/dump-before
python -m scanner dump --file results/dumps/after.sql --label after --out results/scanner/dump-after
python -m scanner files --file results/dumps/before.sql --label before --out results/scanner/text-before
python -m scanner files --file results/dumps/after.sql --label after --out results/scanner/text-after

# Sesudah selesai, hapus kredensial dari sesi terminal:
Remove-Item Env:SCANNER_DATABASE_URL
Remove-Item Env:SCANNER_TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

Path dump di atas adalah contoh lokasi yang harus disesuaikan; scanner tidak
membuat dump atau menerapkan proteksi. Pada Linux/bash gunakan `export` untuk
environment dan padanan `make scan`, `make scan-dump FILE=... LABEL=...`,
`make scan-eval LABEL=...`, `make scanner-test` setelah aktivasi environment.

## Saran berikutnya

Verifikasi faktor lingkungan, tujuan retensi, kebutuhan pencarian dan allowed_roles
bersama pemilik sistem; isi ground truth independen, ukur hasil mentah serta
baseline, lalu revisi kamus/ambang berdasarkan kesalahan yang dicatat. Jalankan
ulang before/after pada dump yang mewakili kontrol aktual dan periksa seluruh
turunan identitas. Angka k-anonymity bukan jaminan anonimitas universal.

## Ringkasan verifikasi lokal

- `scanner/.venv/Scripts/python.exe -m pytest scanner/tests -q`: **127 passed,
  1 skipped**. Yang dilewati hanya integrasi database karena
  SCANNER_TEST_DATABASE_URL belum diatur. Test query database memakai mock untuk
  memeriksa quoting identifier, query agregat tanpa LIMIT, dan fallback metadata
  FK; hasil mock bukan validasi isi database asli.
- Fixture sintetis membuktikan deteksi email, telepon, identifier 14 digit,
  rekening, tanggal, alamat ketika semua nama kolom menjadi col_01 dst.; relasi
  duplikat masih ditemukan. Fixture ditulis oleh generator lokal di conftest.py.
- Relasi nama, username/email, pemegang rekening, kota/alamat, offset aritmetika,
  dan kehadiran tanggal iff kategori diuji tanpa hardcode pada logika scanner.
- Parser MySQL backtick, PostgreSQL INSERT/COPY, escape dasar, komentar dan
  pg_dump restrict/unrestrict diuji. Reservoir kecil tetap menghasilkan angka
  k-anonymity seluruh dump, dan file sementara dibersihkan.
- Output enam artefak utama dan findings.csv diuji agar tidak memuat nilai
  pribadi fixture lengkap; pesan error diuji agar tidak menampilkan secret atau
  traceback. Kasus regex menipu dibandingkan baseline; metrik evaluasi diuji
  dengan jawaban yang diketahui. Konfigurasi after dan batas temuan files diuji.
  Konteks kolom spesifik seperti biometrik tetap diusulkan sebagai spesifik dan
  needs_review saat pola isi generik lebih kuat daripada nama kolom.
- `python -m pip check`: tidak ada dependensi rusak. Bantuan CLI dan pemeriksaan
  whitespace Git lolos. GNU Make tidak tersedia di PATH pada mesin sesi ini;
  target scanner-test berisi tepat `python -m pytest scanner/tests -q` yang
  dijalankan lewat environment lokal di atas.
- Belum ada klaim precision/recall pada data panitia, keberhasilan provisioning
  role pada server asli, atau verifikasi angka 730/734. Pengguna akan menjalankan
  validasi asli dengan perintah di bagian sebelumnya.

## Perubahan v1.0 → v1.1.0 dan alasannya

Dasar perubahan adalah run pertama `results/scanner/before_v1/`: no_ktp masih
identifier_lain; nama_bank/nama_kppn menjadi nama auto_accept; tanggal_pernikahan
menjadi tanggal_lahir dan sumber banyak functional semu; jumlah_anak dianggap
spesifik; id surrogate mendapat saran enkripsi; semua kolom P0/P1 akibat impact
lingkungan 5. Duplikat nama diberi delete dan alasan turunan berulang. Data run
lama hanya dibaca; fixture regresi tetap dibuat sendiri, tanpa nilai panitia.

1. **NIK nonstandar:** kamus mencakup ktp, no_ktp, nik, kependudukan. Label nik
   non-16 digit memerlukan >=3 observasi non-NULL, seluruhnya digit, panjang
   tetap dan unik per baris, plus kata kunci nama. Catatan panjang tidak baku
   mempertahankan needs_review. Tanpa kata kunci, identifier nonstandar yang
   ambigu tetap identifier_lain + needs_review. Nama NIK tanpa bukti tidak
   auto_accept. Konteks bank umum tidak mengalahkan bukti NIK bernama yang valid;
   rekening tetap tidak salah menjadi NIK.
2. **Kardinalitas nama:** rasio unik <0.2 **atau** jumlah unik <=20 menutup
   kandidat nama orang dan mengarah ke kategori. Aturan ini sengaja konservatif
   pada sampel kecil: bahkan 20 nama berbeda belum cukup untuk label nama.
   Batas 20/21 dan rasio rendah diuji terpisah, termasuk Bank BCA/KPPN.
3. **Tanggal dan keluarga:** tanggal_pernikahan menjadi jenis tersendiri.
   Pola tanggal + nama pernikahan didukung pencarian kehadiran iff kategori;
   NULL acak tanpa konteks perkawinan tidak cukup untuk menyimpulkan pernikahan.
   Hitungan bernama jumlah/count/total/number/num yang berisi bilangan nonnegatif
   menjadi keluarga, umum, needs_review. Catatan menyatakan ini bukan data anak
   individual. Data individual seperti nama_anak tetap spesifik.
4. **Surrogate ID:** nama persis id, tipe penyimpanan integer, >=3 observasi
   non-NULL unik dan berurutan (urutan baris diabaikan) menjadi operasional,
   non_pribadi, retain, dengan catatan kunci penghubung. Tiga faktor intrinsik
   bernilai 1. Ini kandidat berdasarkan sampel, bukan verifikasi constraint PK;
   sampel acak parsial yang memiliki celah tidak otomatis dinyatakan berurutan.
5. **Prioritas per jenis:** impact.yaml menyimpan sensitivity dan impact 1–5
   per jenis, default dan asumsi nama pejabat publik. Opsional --impact memilih
   kebijakan lain; seluruh kebijakan ikut metadata. Faktor volume/exposure/recovery
   tetap dari environment, sementara exploitability memakai isi. CSV menyimpan
   keenam faktor, dan total/rentang P0–P3 tetap persis. Legacy impact environment
   diabaikan dengan penanda eksplisit agar tidak mengalahkan kebijakan per jenis.
6. **Functional dependency:** rasio sumber dihitung dari nilai non-NULL.
   Rasio >0.9 dikecualikan dari functional dan dilaporkan satu kali per kolom
   pada near_unique_quasi_identifiers, termasuk jumlah unik/observasi/rasio.
   Ambang tepat 0.9 masih diperbolehkan. Ini menghilangkan dependency semu dari
   tanggal pernikahan yang hampir unik di antara baris yang terisi.
7. **Konsistensi turunan:** recommendation menjadi review_minimization, tanpa
   keputusan delete otomatis; consistent_protection_with mencatat kolom sumber,
   dan reason sekali saja memuat “perlakuan masking/akses harus konsisten dengan
   kolom sumber, jika tidak kontrol dapat dilewati”. Nama orang diprioritaskan
   atas username sebagai sumber, termasuk saat nilainya sama setelah normalisasi.
   Password tetap wajib hash; catatan relasi dan konsistensi tetap dicatat.
8. **Nama dan tanggal lahir:** nama publik default retain+mask_for_analyst,
   bukan hash yang rentan kamus. Tanggal lahir default generalize_for_analyst
   (tahun/kelompok usia), dan reason memuat jumlah baris unik dari k-anonymity
   satu kolom seluruh sumber. Pengukuran tidak tersedia ditandai eksplisit.
9. **K-anonymity minimal:** JSON menyimpan semua hasil, urut ukuran 1,2,3 lalu
   jumlah baris unik menurun. HTML menyembunyikan superset pada tabel sama jika
   subset unik >=95%, dan menampilkan maksimal 15 hasil setelah filter.
   Run v1 mencatat tanggal_lahir saja memiliki 700/734 baris unik (>95%); karena
   itu kombinasi tanggal_lahir+tempat_lahir+jenis_kelamin dapat tidak muncul di
   HTML v1.1, tetapi tetap dapat diperiksa di JSON. Penyaringan bukan penghapusan
   agregat ataupun perubahan pemilihan kandidat yang dihitung.
10. **Laporan dan versi:** tabel ringkas tujuh kolom ada di atas inventaris
    lengkap; CSS cetak A4 landscape, alasan membungkus baris, thead berulang,
    dan overflow area tabel dibuka ketika dicetak. Versi 1.1.0 serta daftar
    change_summary disimpan pada setiap run_meta.json, termasuk baseline/files.

**Batas matematis P3:** environment_before tetap volume=3, exposure=5,
recovery=5. Dengan tiga faktor lain paling rendah 1, minimum total adalah
3+5+5+1+1+1=16, yaitu P2. Karena itu v1.1 menyebar prioritas before menjadi
P0/P1/P2, termasuk operasional pada kelompok terendah P2; tidak memaksa P3 dengan
mengubah total atau faktor lingkungan. Contoh after 3/2/3 memungkinkan total
11 (P3) untuk operasional. Keempat tingkat diuji lintas konfigurasi dan batas
12/13, 18/19, 24/25. P3 pada baseline memerlukan penilaian ulang faktor lingkungan
yang nyata oleh tim; nilainya tidak diubah diam-diam untuk meratakan distribusi.

**Verifikasi v1.1:** seluruh perubahan perilaku memiliki regresi di
test_v11_detection.py, test_v11_priority.py, test_v11_relations.py dan
test_v11_reporting.py. Suite lama masking/parser/SQL/evaluasi/kebocoran tetap
dijalankan. Smoke test Chrome headless pada laporan sintetis menghasilkan PDF
dengan MediaBox 841.92×594.96 pt (A4 landscape); tampilan tabel ringkas juga
diperiksa dari screenshot. Browser hanya dipakai untuk memeriksa artefak lokal,
bukan dependensi scanner atau klasifikasi.

Untuk validasi ulang dari sesi PowerShell yang sudah mengatur kredensial:

```powershell
.\scanner\.venv\Scripts\python.exe -m pytest scanner/tests -q
.\scanner\.venv\Scripts\python.exe -m scanner --version
.\scanner\.venv\Scripts\python.exe -m scanner db --schema public --sample 1000 --label before --out results/scanner/before_v1_1
```

Jangan menimpa before_v1/. Bandingkan inventory.csv dan relations.json v1.1,
periksa reason tanggal lahir terhadap agregat satu kolom JSON, dan pastikan
run_meta memuat scanner_version 1.1.0, change_summary, tiga faktor lingkungan,
dan type_priority_policy. Hasil scan baru pada database asli tetap dikerjakan
pengguna; pengujian lokal tidak membuktikan klasifikasi isi asli telah benar.

## Langkah 4 — 27 Oktober 2026, implementasi evaluasi

- Perbaikan A1–A8 yang sudah ada dipakai ulang bersama regresinya. Tambahan: identifier
  numerik anonim 14/15/18 digit tidak dikonfirmasi sebagai NIK/NPWP tanpa konteks;
  tetap identifier_lain + needs_review. Alias noKTP/nomorNIK ada di kamus generik.
- Kategori institusi diberi non_pribadi hanya dengan bukti isi bank/kantor KPPN
  yang kuat (>=80%) serta kardinalitas rendah, bukan dari nama kolom saja.
  Kategori orang seperti jenis kelamin tetap umum. Kode bank yang hampir unik
  tetap kandidat pribadi; konvensi label institusi Alby dan keputusan FIN pada
  kontrak tetap dipisahkan dari hasil deteksi, tidak dipaksa agar akurasi sempurna.
- Label map YAML hanya diimpor evaluator. Taksonomi Alby dipetakan ke tipe native,
  termasuk tanggal_pernikahan, keluarga, kategori institusi, dan identifier_lain.
  Ground truth/metodologi tidak diedit. Label tidak dikenal tampil pada unmapped_labels,
  tidak dikeluarkan dari denominator dan tidak dianggap benar hanya karena teksnya sama.
- Evaluator menormalisasi boolean/kelas PDP serta public sebagai schema default,
  menolak kunci duplikat/CSV tidak lengkap, mengecualikan prediksi tidak berlabel,
  dan menyimpan F1/F2, confusion matrix, akurasi, daftar ketidakcocokan, serta hash input.
  Semua hasil in_sample=true; missing prediction tetap berada dalam denominator.
- Regex_only memerlukan skor nama nol dan kecocokan isi >=60 untuk tipe regex yang
  didukung. Aturan dibekukan sebelum evaluasi; kolom tanpa kecocokan tidak dihitung
  terdeteksi hanya karena default pdp_class umum. Kelas/tipe mentah tetap dievaluasi
  terpisah. Mode ini melewati relasi dan agregat k-anonymity untuk menghemat pekerjaan.
- Eksekusi hanya pada sumber 734 baris; tidak ada benchmark, scan 100k/1M, perubahan
  sumber/role/password, atau start/stop container. Credential scanner_user tidak ada
  di env sesi agen; credential admin lab yang telah diotorisasi dipakai untuk login
  dengan startup role=scanner_user dan default_transaction_read_only=on. Effective
  role scanner_user, larangan UPDATE, dan transaksi read-only diperiksa; ini bukan
  bukti autentikasi password scanner_user. Detail tanpa DSN ada di step4_preflight.json.
- Perintah PowerShell tersedia di scanner/README.md. Hasil run/test dan keterbatasan
  aktual dicatat pada evidence/scanner/, dengan checksum v1 dan ground truth dijaga.

## Hasil langkah 4 yang benar-benar dijalankan

27 Oktober 2026, kode dibekukan pada `12e4064a399c2eef26e043c8de8a39c566f093be`.
Scan gabungan 734 baris selesai **7,313 detik**, regex_only **0,909 detik**.
Keduanya versi 1.1.0; tabel/sampel sama, 30 prediksi dibandingkan dengan 29 label
(id tidak dinilai). Seluruh 25 label taksonomi Alby terpetakan, tanpa missing prediction.
Hasil v1 memakai berkas historis asli dan dinilai ulang dengan evaluator yang sama.

| Metode | Precision | Recall | F1 | F2 | Akurasi tipe | Akurasi kelas |
|---|---:|---:|---:|---:|---:|---:|
| v1 | 89,66% | 100% | 94,55% | 97,74% | 75,86% | 86,21% |
| v1.1 | 96,30% | 100% | 98,11% | 99,24% | 89,66% | 96,55% |
| regex_only | 100% | 42,31% | 59,46% | 47,83% | 31,03% | 68,97% |

- Seluruh evaluasi **in_sample=true**. V1.1: TP=26, FP=1, FN=0, TN=2.
  FP tersisa adalah kode_bank terhadap konvensi label institusi; perbedaan tipe
  lain pada pekerjaan_terakhir dan ruangan. Ketiganya disimpan di mismatches;
  aturan tidak diubah lagi setelah melihat hasil ini. Domain FIN kode_bank tetap
  mengikuti kontrak. Regex_only melewatkan 15 atribut pribadi, termasuk email yang
  rasio kecocokan pola penuhnya di bawah ambang tetap 60; keterbatasan baseline
  regex dibedakan dari bukti nilai keseluruhan aman.
- Prioritas sebelum: **P0=10, P1=10, P2=10**, P3=0 sesuai batas matematis
  faktor lingkungan lama, tanpa mengubah ambang prioritas. Enam faktor tetap
  tersimpan per kolom. P3 diuji pada konfigurasi lain oleh regresi prioritas.
- JSON k-anonymity menyimpan **298 kombinasi**; kombinasi tempat_lahir +
  tanggal_lahir + jenis_kelamin tetap mencatat **730/734 unik**. Supersetnya
  disembunyikan di HTML karena tanggal_lahir tunggal sudah unik >=95%.
  Ringkasan HTML dibatasi 15 hasil setelah filter; JSON tetap lengkap.
- Test final: **188 lulus, 0 gagal/error/skip**, termasuk integrasi transaksi read-only
  dan test_disguised_names (24 fixture buatan sendiri, enam tipe terdeteksi dengan
  confidence >=60, name_score=0 dan relasi turunan tetap ditemukan).
  JUnit lokal di results/scanner/step4-tests.xml, ringkasan di evidence/scanner/tests.json
  dan disguised_names.json. Tidak memakai baris dump sebagai fixture.
- Audit keluaran baru mencari **10.645 nilai lengkap berbeda** dari sumber,
  panjang >=6 pada kolom selain referensi yang dinyatakan: **0 kecocokan**.
  Ini pemeriksaan nilai utuh dalam keluaran scanner saja, bukan scan S06 seluruh
  sistem; nilai pendek, prefiks termasking dan inferensi tetap di luar kesimpulan.
- Checksum sumber 734, kedua berkas ground truth/metodologi, serta empat artefak
  before_v1 tetap sama. Snapshot baseline dan hasil benchmark tidak disentuh.
  step4_validation.json memuat pemeriksaan serta hash seluruh artefak scan baru.
- Evidence utama: before_v1_1/; before_regex_only/; evaluation_v1.json;
  evaluation_v1_1.json; evaluation_regex_only.json; comparison.json/CSV.
  evaluation.json adalah salinan identik evaluasi v1.1 untuk konsumen prompt C.
  Seluruh hasil adalah prediksi mentah sebelum tinjauan manusia.
