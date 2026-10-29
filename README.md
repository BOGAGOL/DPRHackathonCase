# Pelindungan Data Pribadi

Solusi ini melindungi data pribadi anggota dengan enkripsi pada tingkat field,
pemisahan kunci dari database, dan pembatasan akses melalui aplikasi web. Tujuannya
adalah mengurangi nilai informasi dari salinan database yang bocor, sambil
mempertahankan pencarian, pelayanan pengguna yang berwenang, serta pemulihan layanan.

Alurnya dimulai dari assessment data, menghasilkan profil perlindungan, lalu
memigrasikan data ke PostgreSQL terproteksi. Aplikasi FastAPI dan Next.js melayani
enam peran pengguna. OpenBao mengelola kunci pembungkus; backup dienkripsi dengan
kunci terpisah. Pengujian mencakup ketepatan migrasi, pembatasan akses, simulasi
kebocoran, integritas backup, pemulihan, dan dampak kinerja.

**Tim: tetapi di Depok saya sampaikan saya akan lawan**

- Ahmad Dzulfikar As Shavy
- Muhammad Albyarto Ghazali
- Favian Zhafif Rizqullah Permana

Panduan ini ditujukan kepada juri dan pengelola yang ingin mencoba, memasang, dan
memeriksa solusi. Seluruh perintah dijalankan dari folder utama repositori, yaitu
folder yang berisi `README.md` ini.

## Pilih cara evaluasi

| Tujuan | Cara memulai | Yang diperoleh |
|---|---|---|
| Memahami hasil tanpa instalasi | Buka [docs/RESULTS.html](docs/RESULTS.html) di browser | Penjelasan hasil, grafik, kegagalan, keterbatasan, dan tautan data mentah; dapat dibaca offline |
| Mencoba aplikasi yang dideploy | [Buka aplikasi HTTPS](https://43.156.157.247/login), gunakan [accounts.md](accounts.md) | Antarmuka layanan dan perbedaan hak enam akun; lihat status akses di bawah |
| Menguji alur lengkap secara mandiri | Ikuti [instalasi lokal](#instalasi-lokal-dan-demo-734-record), lalu jalankan `demo` | Import 734 record, assessment, hardening, aplikasi HTTPS, pengujian, dan demo interaktif |
| Mengulang pengujian tanpa demo interaktif | Jalankan `verify` setelah `setup` | Stack sementara diuji, hasil disimpan, lalu layanan dihentikan |

**Status deployment yang tercatat:** pemeriksaan 29 Oktober 2026 menemukan halaman
HTTPS tersedia, tetapi login browser ditolak HTTP403. Diagnostik menunjukkan
ketidakcocokan konfigurasi Origin pada VM; akun yang sama berhasil pada diagnostik
non-browser. Hasil tersebut belum membuktikan login deployment pulih. Demo lokal
berjalan terpisah dan mempunyai bukti pengujian lulus. Status dan bukti dapat
dibaca pada [halaman hasil](docs/RESULTS.html#service); perbaikan runtime dijelaskan
dalam [panduan operator](docs/OPERATIONS.md#login-browser-ditolak-http403).

## Cara kerja dan ruang lingkup

![Arsitektur sistem](docs/architecture/architecture.svg)

1. **Assessment.** Scanner membaca metadata dan sampel data, lalu menghasilkan
   inventaris, klasifikasi, dan risiko. Keputusan perlindungan disusun dari
   inventaris dengan override yang eksplisit dan alasan per kolom.
2. **Hardening.** Dari 29 kolom sumber, 25 field dienkripsi menggunakan
   AES-256-GCM: 21 dalam domain identitas/PII dan 4 dalam domain keuangan/FIN.
   Empat kolom referensi/REF dipertahankan sesuai profil. Kunci data dibuat per
   record dan domain, dibungkus oleh OpenBao, lalu disimpan dalam bentuk terbungkus.
   AAD mengikat ciphertext ke record dan kolomnya. Tiga blind index memungkinkan
   pencarian nilai yang sama persis tanpa menyimpan nilai pencarian sebagai plaintext.
3. **Layanan.** Backend memeriksa peran dan assignment record sebelum mengirim data.
   Masking dan penghilangan field dilakukan sebelum JSON mencapai browser.
   Analis hanya menerima agregat dengan jumlah anggota minimal lima per kelompok.
4. **Pemulihan dan pembuktian.** Migrasi didekripsi dan dibandingkan kembali di
   memori. Backup mengalir langsung dari `pg_dump` ke enkripsi tanpa file dump
   plaintext sementara. Restore, perubahan satu byte, dan pemulihan aplikasi diuji.

Web merupakan bagian dari solusi. Assessment, migrasi, backup/restore, simulasi
kebocoran, dan benchmark dijalankan melalui command line. Diagram menunjukkan
pemisahan komponen; demo lokal menggunakan port acak pada mesin evaluator.

## Instalasi lokal dan demo 734 record

### Prasyarat

| Komponen | Kebutuhan |
|---|---|
| Python | 3.11 atau lebih baru; modul `venv` dan `pip` tersedia |
| Node.js dan npm | Node.js minimal 20.9; npm tersedia di `PATH` |
| Docker | Engine Linux aktif dan Compose V2; Windows dapat memakai Docker Desktop |
| Browser | Google Chrome terpasang, termasuk untuk pengujian browser otomatis |
| Dataset | File privat `02_data.sql` dari panitia, berisi 734 record |
| Koneksi | Internet saat pemasangan dependency dan pengunduhan image |

Gunakan akun OS biasa. Pada Linux, jangan menjalankan launcher sebagai `root`.
Installer resmi tersedia melalui [Python](https://www.python.org/downloads/),
[Node.js](https://nodejs.org/en/download), [Docker](https://docs.docker.com/get-started/get-docker/),
dan [Chrome](https://www.google.com/chrome/).

Dataset tidak disertakan dalam distribusi sumber publik. Letakkan `02_data.sql`
di folder privat di luar repositori, misalnya `C:/private/02_data.sql` pada Windows
atau `/home/evaluator/private/02_data.sql` pada Linux. Ganti contoh path pada
perintah berikut dengan lokasi file yang sebenarnya. Launcher membaca literal
INSERT yang didukung dari dataset tersebut, bukan menjalankan SQL bebas.

Jika file sudah tersedia pada `sql/baseline/02_data.sql` dalam salinan privat,
argumen `--data` boleh dihilangkan. Tidak perlu menyalin `.env`, password database,
token, atau konfigurasi komputer pembuat solusi.

### 1. Periksa perangkat dan pasang dependency

Pada PowerShell/Windows:

```powershell
python --version
node --version
npm --version
docker info
docker compose version
python -m infra.reproduce setup
```

Pada Linux:

```bash
python3 --version
node --version
npm --version
docker info
docker compose version
python3 -m infra.reproduce setup
```

`docker info` harus berhasil menghubungi engine. `setup` membuat `.venv` dan
`.venv-assessment`, memasang dependency yang dideklarasikan, menjalankan `pip check`,
kemudian menjalankan `npm ci` dan build frontend. Pemisahan environment diperlukan
karena dependency layanan dan assessment berbeda. Tahap ini belum membuat database
atau mengakses kunci. Tunggu pesan **`Setup PASS`** sebelum melanjutkan.

### 2. Jalankan alur lengkap dan buka demo

Windows:

```powershell
python -m infra.reproduce demo --data "C:/private/02_data.sql"
```

Linux:

```bash
python3 -m infra.reproduce demo --data "/home/evaluator/private/02_data.sql"
```

Satu perintah ini menjalankan urutan berikut. Tidak perlu menjalankan script setiap
modul secara manual.

| Tahap | Yang dijalankan | Hasil yang diperiksa |
|---|---|---|
| Persiapan layanan | PostgreSQL 18, OpenBao 2.5.5, CA lokal, TLS, dan kredensial baru | Layanan siap dan koneksi tervalidasi |
| Import | Membaca dataset ke database sumber baru | Tepat 734 record |
| Assessment | Scanner, klasifikasi, dan penyusunan protection profile | Inventaris 29 kolom dan keputusan perlindungan |
| Hardening | Skema/role, kunci per record, enkripsi, blind index, dan migrasi | Seluruh 734 record dibandingkan dengan sumber; percobaan resume tidak menggandakan data |
| Service application | Akun dan assignment untuk enam peran | Aplikasi memakai database terproteksi |
| Security verification | TLS, izin DB, RLS, kripto, backup/restore, tamper, retensi, dan browser | Pemeriksaan positif serta negatif, termasuk aplikasi pada database hasil restore |

Setelah pengujian berhasil, terminal menampilkan:

```text
Demo: https://localhost:<port-acak>/login
Private accounts: <path-privat>/service-b/service-b-protected-accounts.json
Local browser CA: <path-privat>/tls/ca.crt
Ctrl+C stops ONLY this demo. Runtime token expires after 1 hour.
```

Gunakan URL yang **benar-benar dicetak**, termasuk portnya. Biarkan terminal tetap
terbuka selama mencoba aplikasi. Akun lokal dibuat acak pada setiap run; buka file
yang ditunjukkan oleh `Private accounts` dengan editor lokal untuk melihat pasangan
`role`, `username`, dan `password`. `accounts.md` digunakan untuk deployment publik,
sehingga kredensialnya berbeda dari demo lokal.

Setiap run mempunyai database, kunci, dan port loopback baru. Launcher tidak
menggunakan `pg-dpr` existing dan tidak mengubah deployment. Init/unseal otomatis
hanya berlaku untuk OpenBao baru milik demo sementara. Instalasi permanen memakai
prosedur custody dan unseal manual pada [panduan operasi](docs/OPERATIONS.md).

### 3. Percayai sertifikat lokal untuk akses browser manual

Demo menggunakan HTTPS dengan CA lokal baru. Gunakan file **`ca.crt` dari run yang
sedang aktif**, sesuai path `Local browser CA`. CA tidak dipasang otomatis ke OS.

- **Windows:** buka `ca.crt`, pilih **Install Certificate → Current User → Place
  all certificates in the following store → Trusted Root Certification Authorities**.
  Konfirmasikan pemasangan CA demo tersebut, lalu buka kembali Chrome dan URL demo.
  Pemasangan juga tersedia melalui [Import-Certificate dari Microsoft](https://learn.microsoft.com/en-us/powershell/module/pki/import-certificate).
- **Chrome/Linux:** buka `chrome://certificate-manager`, lalu impor CA pada
  pengaturan sertifikat lokal yang dipercaya untuk server. Pada versi dengan menu
  lama, gunakan `chrome://settings/certificates` dan bagian **Authorities**.
  Rujuk [pengelolaan trust lokal Chrome](https://chromium.googlesource.com/chromium/src/+/main/net/data/ssl/chrome_root_store/faq.md)
  jika label menu berbeda.

Sesudah demo, hapus kembali **sertifikat CA run tersebut** dari daftar CA yang
dipercaya. Run berikutnya memakai CA baru. Jangan mengimpor `ca.key`/`server.key`
atau menonaktifkan pemeriksaan TLS untuk melewati peringatan browser.

Uji Chrome otomatis tidak memerlukan pemasangan CA ke OS: uji mem-pin sertifikat
sementara yang tepat. Klien PostgreSQL/OpenBao dan komunikasi antarservice tetap
memverifikasi CA; tidak ada penonaktifan verifikasi TLS global.

### 4. Selesai, hentikan demo, dan baca hasil run

Tekan **Ctrl+C** satu kali pada terminal demo. Layanan milik run dihentikan, lalu
terminal menampilkan ringkasan **LULUS/GAGAL**, hasil tiap tahap, dan lokasi:

```text
evidence/reproduction/<run-id>/report.html
```

Buka file tersebut di browser. Pada mode `demo`, laporan akhir ditulis **setelah
demo dihentikan**. Token demo mempunyai masa berlaku satu jam; mulai run baru jika
masa berlaku habis. Dataset input dan hasil pengujian tidak dihapus oleh Ctrl+C.
Volume Docker milik demo dibersihkan saat penghentian normal; direktori privat run
di folder sementara OS tetap tersimpan dengan akses terbatas, termasuk material
pemulihan. Direktori privat itu bukan bagian dari sumber yang didistribusikan.

### Alternatif: pengujian otomatis tanpa mempertahankan web

Setelah `setup`, gunakan perintah berikut sebagai pengganti `demo`:

```powershell
python -m infra.reproduce verify --data "C:/private/02_data.sql"
```

Pada Linux gunakan `python3` dan path input Linux. Pemeriksaan yang sama dijalankan,
layanan dihentikan otomatis, dan `report.html` langsung tersedia setelah selesai.
Exit code `0` berarti lulus; selain itu berarti gagal. Tidak perlu menjalankan
`verify` sebelum `demo`, karena `demo` sudah menyertakan verifikasi yang sama.

Jika GNU Make tersedia, padanan command adalah `make setup`,
`make demo DATA="C:/private/02_data.sql"`, `make verify DATA="C:/private/02_data.sql"`,
`make test`, dan `make results`. Pada Linux dapat ditambahkan `PYTHON=python3`.
Make bersifat opsional; perintah Python di atas adalah antarmuka lintas platform.

### Alternatif layanan native

Jika Docker tidak tersedia, sediakan binary PostgreSQL **18** dan OpenBao **2.5.5**
dari [distribusi PostgreSQL](https://www.postgresql.org/download/) dan
[rilis OpenBao](https://github.com/openbao/openbao/releases/tag/v2.5.5), lalu
verifikasi checksum unduhannya. Kedua path native wajib diberikan bersamaan:

```powershell
python -m infra.reproduce demo --data "C:/private/02_data.sql" --native-pg-bin "C:/tools/pgsql/bin" --native-bao-bin "C:/tools/bao.exe"
```

Folder PostgreSQL harus memuat `postgres`, `initdb`, `pg_ctl`, `psql`, `pg_dump`,
dan `pg_restore`. Argumen yang sama berlaku untuk `verify`; pada Linux sesuaikan
path dan nama executable. Launcher membuat cluster baru, bukan memakai cluster
PostgreSQL native yang sudah berisi data.

**Cakupan bukti runtime:** pengujian bersih yang tersimpan berhasil melalui jalur
native PostgreSQL 18/OpenBao dengan TLS. Engine Docker pada host uji terakhir
mengalami error; keberhasilan native tidak dinyatakan sebagai keberhasilan runtime
Docker atau semua sistem operasi.

## Demonstrasi aplikasi dan hasil yang diharapkan

Langkah berikut berlaku untuk web deployment jika login tersedia, atau demo lokal
setelah pesan `Demo:` muncul. Untuk deployment gunakan [accounts.md](accounts.md);
untuk lokal gunakan file akun run. Klik **Keluar** sebelum berpindah akun, atau
gunakan profil browser terpisah.

Pada halaman `/login`, isi **Username** dan **Password**, lalu klik **Masuk ke
aplikasi**. Menu di sebelah kiri menyesuaikan hak akun. Tombol keluar berupa ikon
di kanan atas dengan label **Keluar**.

| Urutan | Akun dan tindakan | Hasil yang diharapkan |
|---|---|---|
| 1 | `operator`: buka **Daftar anggota**, pilih detail record yang tersedia | Hanya record assignment yang terlihat. Identifier/kontak dimasking sesuai policy; field FIN tidak dikirim |
| 2 | `privileged_officer`: buka record assignment yang sama | PII sesuai izin dapat dibaca; FIN tetap tidak dikirim |
| 3 | `finance_officer`: bandingkan record assignment yang sama | FIN tersedia; identitas tertentu tetap dimasking. Akses data anggota bersifat read-only |
| 4 | `anggota`: buka profil/data sendiri, lalu coba URL detail record lain yang diketahui dari akun staf | Data sendiri tersedia; record orang lain ditolak tanpa mengungkap keberadaannya |
| 5 | `analyst`: buka **Ringkasan agregat**, pilih dimensi dan klik **Terapkan**, lalu coba `/anggota` atau URL detail | Hanya kelompok berjumlah ≥5 yang ditampilkan; label kelompok 1–4 juga tidak dikirim. Data per record ditolak; total keseluruhan tidak disediakan |
| 6 | `auditor`: buka **Log audit**, kemudian coba data anggota | Metadata aktivitas tersedia; isi data anggota ditolak |

Jumlah record pada daftar mengikuti assignment akun, sehingga tidak harus 734.
Gunakan record yang ditugaskan kepada akun yang sedang diuji. Pada penolakan,
antarmuka dapat menampilkan pesan tidak berhak/tidak ditemukan; API memberikan
penolakan sesuai endpoint. [Matriks izin lengkap](docs/ACCESS_CONTROL.md).

**Pencarian:** pada akun staf yang berizin, buka **Pencarian identitas**, pilih
Nomor KTP atau Email, lalu masukkan nilai yang diketahui dari record assignment.
Pencarian memakai kesamaan nilai setelah normalisasi, bukan pencarian sebagian
kata. Hasil tetap dibatasi scope akun; blind index tidak memberi akses tambahan.

**Periksa respons:** bila ingin memeriksa bahwa masking bukan sekadar tampilan,
buka Developer Tools → Network, pilih respons API detail, dan periksa JSON.
Field FIN harus tidak ada untuk operator/privileged officer/anggota; nilai yang
dimasking harus sudah termasking dalam respons. Jangan menyalin data sensitif
atau kredensial ke hasil publik. Pemeriksaan cookie, JSON, dan browser storage
juga dijalankan oleh uji otomatis.

**Demonstrasi perubahan data:** gunakan demo lokal, misalnya ubah kontak sendiri
dengan akun yang berizin dan lihat metadata aktivitas melalui auditor. Hindari
mutasi pada deployment bersama. Percobaan penghapusan untuk retensi dilakukan
otomatis pada record sintetis terpisah; tidak menghapus anggota sumber.

Untuk menjelaskan pelindungan salinan database dan pemulihan, lanjutkan ke
[halaman hasil](docs/RESULTS.html#security). Bandingkan skenario tanpa kunci,
kompromi kemampuan domain, hasil tamper-backup, dan hasil restore. Kontrol tersebut
dibuktikan melalui pengujian teknis, bukan hanya melalui tampilan web.

## Membaca hasil pengujian

[docs/RESULTS.html](docs/RESULTS.html) merangkum pengukuran yang sudah tersimpan
dalam bahasa biasa. Halaman itu menjelaskan arti metrik, menampilkan grafik dan
tabel, serta menautkan bukti. Untuk menyusunnya kembali dari data yang sama:

```powershell
python -m infra.reproduce results
```

Perintah mencetak path halaman yang harus dibuka; tidak membuka browser atau
menjalankan benchmark baru. Bukti run yang baru dibuat berada di direktori
`evidence/reproduction/<run-id>/` masing-masing:

| File | Cara membacanya |
|---|---|
| `report.html` | Ringkasan manusia: LULUS/GAGAL dan status setiap tahap |
| `summary.json` | Ringkasan yang sama dalam format mesin, waktu, transport, dan tahap gagal jika ada |
| `scanner/`, `protection_profile.yaml` | Hasil assessment dan alasan perlindungan per kolom |
| `migration.json` | Jumlah record yang dibandingkan, validasi, dan resume |
| `security.json`, `browser.json` | Hasil kontrol keamanan dan pemeriksaan enam akun |
| `backup.json`, `restore-without-openbao.json`, `restore-with-openbao.json` | Backup serta pemulihan ciphertext dan layanan dengan akses kunci |
| `tamper.json`, `retention.json` | Penolakan backup yang diubah dan ketidakhadiran record sintetis yang dihapus pada backup baru |

**PASS/LULUS** berarti pemeriksaan yang dijalankan memenuhi asersi pada lingkungan
tersebut. **FAIL/GAGAL** berarti ada kegagalan atau prasyarat tidak terpenuhi.
**NOT_RUN/skip** berarti belum dijalankan, sehingga bukan bukti lulus. File tertentu
dapat belum ada jika run terhenti pada tahap awal. `false` pada
`decryption_smoke.performed` untuk restore **tanpa** OpenBao adalah perilaku yang
disengaja: ciphertext dipulihkan tanpa mencoba membukanya.

### Hasil yang tersimpan dan batas klaimnya

| Aspek | Hasil dan ruang lingkup |
|---|---|
| Alur lokal 734 | Run bersih 29 Oktober 2026 lulus enam tahap; seluruh 734 record dibandingkan, resume diuji, dan 100 pemeriksaan Chrome pada layanan hasil restore lulus |
| Assessment | Precision 96,30%, recall 100%, F1 98,11% terhadap 29 kolom berlabel; evaluasi in-sample |
| Kripto dan akses | Perubahan bit/pertukaran ciphertext ditolak; hak peran/record/field, TLS dan akses analis diuji dalam scope hasil masing-masing |
| Salinan bocor tanpa kunci | Sel sensitif AEAD tidak berhasil dipulihkan pada skenario yang diuji; ini bukan klaim seluruh isi DB tidak membocorkan informasi |
| Backup/restore | Restore dua mode, penolakan artefak yang diubah, dan retensi record sintetis mempunyai bukti pengujian |
| Migrasi besar | Hasil migrasi/validasi 100k dan 1M tersimpan; pengujian demo default tetap 734 |
| Kinerja | Before/after DB/toolkit 100k dan 1M beserta raw tersedia. Target latensi/throughput belum tercapai; target error-rate lulus. Seri benchmark API belum lengkap |
| Deployment publik | Halaman HTTPS tersedia pada pemeriksaan tercatat; login browser belum lulus karena indikasi mismatch Origin runtime |

[Buka laporan run lokal yang lulus](evidence/reproduction/20261029T111814Z-8ff4e56e/report.html)
dan [hasil regresi](evidence/tests/regression.json). Pengujian lokal yang lulus
tidak mengganti label gagal pada hasil deployment atau benchmark.

Blind index mengungkap kesetaraan nilai, sedangkan REF, pola NULL, ukuran dan
metadata tertentu tetap terlihat. Suppression analis bukan differential privacy.
Kompromi aplikasi beserta kemampuan decrypt dapat membuka data sesuai kapabilitas
yang dicuri. RLS berbasis principal transaksi adalah lapisan tambahan; pencuri
kredensial `app_user` dapat mengubah setting principal. Disaster recovery seluruh
key plane, HA, secure erase, dan seluruh log host belum dibuktikan lengkap.
[Model ancaman dan keterbatasan](docs/SECURITY.md) menjabarkan batas tersebut.

## Pengujian tambahan, benchmark, dan operasi permanen

Untuk mengulang suite regresi setelah `setup`:

```powershell
python -m infra.reproduce test
```

Command menjalankan suite inti, aplikasi, dan assessment pada environment masing-
masing. Integrasi eksternal yang belum diaktifkan dilaporkan skip. Gunakan `verify`
untuk pengujian stack nyata 734; unit test saja tidak membuktikan integrasi layanan.

Pemeriksaan integritas sumber dan inventaris dependency pada Windows:

```powershell
.venv/Scripts/python -m infra.distribution check
```

Pada Linux gunakan `.venv/bin/python`. Pemeriksaan sumber tidak menggantikan uji
runtime. [Inventaris dependency dan SBOM](docs/DEPENDENCIES.md) menjelaskan file
di `docs/sbom/` beserta cakupan dan hasil auditnya.

- [Metodologi](docs/METHODOLOGY.md): pembuatan dataset sintetis 100k/1M dengan seed
  tetap, perintah pengukuran, urutan B-P-P-B, target, serta lokasi hasil mentah.
  Benchmark besar dipisahkan dari demo dan tidak dijalankan otomatis.
- [Reproduksi dataset besar dan simulasi kebocoran](docs/METHODOLOGY.md#reproduksi-dataset-besar-dan-simulasi-kebocoran):
  urutan datagen, snapshot privat, before, empat skenario protected, dan budget after.
- [Operasi dan pemulihan](docs/OPERATIONS.md): instalasi permanen, konfigurasi
  privat, TLS, init/unseal manual, role, migrasi, startup aplikasi, backup/restore,
  rotasi kunci, dan penanganan Origin. Gunakan prosedur ini untuk penerapan instansi.
- [Refresh token aplikasi](docs/TOKEN_REFRESH.md): pemasangan broker AppRole dan
  timer opsional pada deployment systemd; masa berlaku token tetap dibatasi dan
  unseal tetap manual. Penerapan pada VM memerlukan verifikasi tersendiri.
- [Spesifikasi teknis](docs/contracts/CONTRACT.md): format ciphertext, AAD,
  normalisasi, skema dan antarmuka antarservice.

## Penanganan kendala

| Gejala | Yang perlu diperiksa |
|---|---|
| `python`/`node`/`npm` tidak dikenali | Pasang prasyarat, buka terminal baru, lalu periksa versi dari folder utama |
| `setup` gagal | Versi Node minimal 20.9, akses unduhan dependency, dan modul Python `venv`/`pip`; setelah diperbaiki ulangi `setup` |
| Engine Docker tidak terhubung/HTTP500/WSL error | Pastikan engine Linux siap dan `docker info` berhasil; gunakan jalur native jika engine belum dapat digunakan |
| Run gagal sebelum import | Periksa path privat dataset, isi 734 record yang didukung, serta keberhasilan build frontend dari `setup` |
| Chrome otomatis tidak tersedia | Pasang Google Chrome; instalasi Playwright saja tidak menggantikan browser Chrome yang dipakai pengujian |
| Peringatan sertifikat pada demo manual | Impor CA run aktif sesuai langkah di atas dan buka URL/port yang dicetak; jangan gunakan CA dari run lama |
| Login lokal tidak cocok | Gunakan file `Private accounts` dari run aktif, bukan akun deployment atau run sebelumnya |
| Login deployment ditolak HTTP403 | Lihat status deployment dan prosedur Origin pada panduan operasi; penonaktifan CSRF/TLS bukan solusi |
| Layanan demo berhenti merespons setelah lama dibiarkan | Token demo berlaku satu jam; hentikan run dan mulai demo baru |
| Verifikasi gagal | Buka `report.html` dan `summary.json` run tersebut; periksa tahap pertama yang gagal. Jangan menganggap NOT_RUN sebagai PASS |

## Struktur sumber

```text
README.md         Panduan instalasi, evaluasi, dan demonstrasi
accounts.md       Akun evaluator untuk deployment web
app/              Backend FastAPI dan frontend Next.js
infra/            TLS, OpenBao/PostgreSQL, launcher, dan alat distribusi
scanner/, policy/ Inventarisasi dan profil perlindungan
migration/, sql/  Migrasi, skema, dan role
toolkit/          Paket kriptografi dprcrypto
scripts/backup/   Backup terenkripsi dan restore
datagen/          Pembangkit dataset sintetis
benchmark/        Pengukuran yang dapat diulang
verify/           Verifikasi kebocoran dan penyaji hasil
evidence/         Hasil pengujian dan hasil mentah
docs/             Arsitektur, spesifikasi, operasi, analisis, dan SBOM
```

Kode menggunakan lisensi [MIT](LICENSE), dokumentasi
[CC BY-NC 4.0](LICENSE-DOCS.md); atribusi pada [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Dataset panitia tidak dipublikasikan. `accounts.md` berisi akun demo yang memang
disediakan untuk evaluator. Kredensial PostgreSQL/OpenBao, root token, unseal key,
SSH, private key sertifikat, dan kunci backup tetap berada di penyimpanan privat.
