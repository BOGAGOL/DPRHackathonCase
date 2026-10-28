# Modul C — konfigurasi verifikasi

Keputusan tim 27 Oktober 2026: dataset panitia `sql/baseline/02_data.sql` boleh
di-commit hanya di repo PRIVATE. Repo tidak boleh dibuat public. Pengecualian S06
ada di `scan_config.toml`, hanya pencocokan path relatif persis setelah normalisasi
pemisah Windows menjadi `/`; bukan pengecualian seluruh folder atau semua SQL.
Gitleaks memiliki regex path berjangkar yang sama. Paket lampiran publik memakai
`export-ignore` di `.gitattributes`; pembuat paket lain wajib membaca daftar pengecualian.

Konfigurasi ini disiapkan sebelum runner S05/S06 diimplementasikan. Test memeriksa
kesesuaian ketiga konfigurasi dan menolak perluasan path yang tidak diminta; belum
merupakan hasil scan repo/riwayat/log. Runner nanti wajib memakai konfigurasi ini
dan merekam pengecualian di evidence, tanpa mengklaim path tersebut telah dipindai.
Known-values/snapshot/credential tetap privat di luar repo. Sumber DB `postgres`
dan hasil benchmark baseline_100k tidak diubah.

## Preflight migrasi laptop benchmark — terblokir sebelum apply TLS

Permintaan pengguna: migrasikan baseline_100k ke protected_100k memakai Modul A,
namun bench_user/scanner_user harus tetap dapat membuka baseline_100k dan
baseline_1m dengan sslmode=disable. Pengguna secara eksplisit meminta BERHENTI
bila updater TLS memaksa semua koneksi tersebut memakai TLS.

Kerja feat/verify-bench sudah aman pada fbeff98 (sudah di-push). File inventaris
lokal anggota lain disimpan via stash bernama "preserve local inventory before
protected_100k migration", tanpa dihapus atau di-commit. Branch beralih ke main,
pull --ff-only berhasil ke 5ab5248f499bae988fefebb774e7ed8e62e8cd87;
commit Modul A 0360af8 merupakan ancestor main itu. README migration, infra,
infra/postgres dan seluruh enable_tls.py sudah dibaca.

Blocker: infra/postgres/enable_tls.py memasukkan kedua baseline dalam DATABASES;
HBA_BLOCK menolak hostnossl bagi user "all" untuk IPv4 dan IPv6. managed_hba
menempatkan blok di awal sebelum aturan lama; tidak ada pengecualian bench_user
atau scanner_user. apply/verify juga menuntut plaintext_rejected untuk setiap
database allowlist, termasuk kedua baseline. Jadi apply akan melanggar kondisi
baseline non-TLS yang diminta, walaupun tidak mengubah baris/tabel baseline.

Berhenti pada audit langkah 1, tanpa menjalankan apply/inspect, mengubah server,
memulai OpenBao, init/unseal, membuat token/credential/CA, prepare/check/run,
atau benchmark. Dependensi root .venv belum dipasang karena blocker ditemukan
pada pembacaan kode sebelum eksekusi setup. Jangan memakai validation hasil
laptop Alby yang sudah ada di main sebagai bukti migrasi pada laptop ini.

Perlu revisi terkoordinasi pada updater A: pengecualian non-TLS yang terbatas
pada dua role dan dua database baseline, dengan metode autentikasi yang sesuai,
di depan reject umum; koneksi aplikasi/protected tetap wajib TLS. Tambahkan uji
positif untuk pasangan role/baseline tersebut dan uji penolakan non-TLS untuk
aplikasi/protected. Kode A/kontrak tidak diubah oleh preflight ini. Hasil mesin:
evidence/migration/laptop-preflight-protected_100k.json, status BLOCKED;
belum ada hasil migrasi lokal atau estimasi durasi 1M yang dapat diukur.

### Pembaruan preflight, 28 Oktober 2026

Keputusan pengguna mengizinkan pengecualian TLS terbatas. Perubahan, test, dan
evidence disposable dikomit terpisah sebagai 61b3110 pada branch
fix/tls-baseline-exception, sudah dipush tanpa merge ke main. Unit infra,
migration, toolkit: 206 lulus / 5 skip; integration TLS disposable: 1 lulus.
Root .venv sudah berisi dependensi README. TLS apply nyata pada pg-dpr PASS,
tanpa restart, dengan pengecualian SCRAM baseline dari IP host Docker
172.17.0.1/32. Empat login baseline non-TLS berhasil; role lain dan app non-TLS
ke protected ditolak. Verify-full ke protected masih menunggu target dibuat.

OpenBao 2.5.5 sudah initialized/unsealed/configured. Hanya token svc-migration
dan svc-app diterbitkan, masing-masing TTL 14400 detik, tanpa default policy,
tidak renewable. Shares, root token, token workload, CA/key dan credential admin
DPAPI berada di C:\dev\dpr-private\openbao, di luar repo; tidak dicetak.
Evidence Alby yang akan diganti dipertahankan dalam subfolder history dengan
penanda main 5ab5248. Preflight lama yang BLOCKED juga diarsipkan, bukan dihapus.

Kendala berikutnya: password scanner_user yang diberikan benar-benar berhasil
autentikasi, tetapi lebih pendek dari minimum 20 karakter pada
infra/protected/credentials.py dan infra/protected/apply.py. Pengguna dimintai
keputusan sebelum rotasi password role tersebut. Tidak ada password diubah;
prepare/check/run belum dijalankan. Baseline 100k/1M dan sumber postgres tetap
memiliki jumlah baris, OID, relfilenode, waktu start, serta counter insert/update/
delete yang sama. Sisa disk 60.45 GiB. Status preflight saat ini
AWAITING_SCANNER_CREDENTIAL_DECISION; belum ada validasi migrasi lokal.

### Selesai migrasi protected_100k di laptop benchmark, 28 Oktober 2026

Pengguna mengizinkan rotasi HANYA password scanner_user. Password baru CSPRNG
48 karakter alfanumerik disimpan DPAPI pada path canonical di luar repo dan
disinkronkan ke credential role Modul A. Password role lain serta atribut role
tetap sama selama rotasi. Koneksi nyata melalui scanner.sources.database ke
postgres (734) dan baseline_100k (100000) lulus read-only tanpa TLS.

Prepare/check PASS, lalu migration run memakai source scanner_user SELECT-only
dan target migration_user dengan TLS verify-full. Run berlangsung
00:38:10.596–00:41:23.158 WIB: **192.562236 detik**, mencakup enkripsi, validasi
decrypt-and-compare semua **100000 baris/semua field**, serta pencabutan token.
Prepare 8.528233 detik dan check 1.153172 detik; jumlah durasi eksekusi tiga
langkah 202.243641 detik (tidak memasukkan jeda/verifikasi antarperintah).
validation-protected_100k.json: passed=true, rows_compared=100000, complete=true.
Null, age_band, REF dan keunikan ketiga blind index tervalidasi. Hash source
migrator menggunakan kanonisasi tersendiri, bukan hash datagen; jangan
membandingkan hash dua format serialisasi yang berbeda secara langsung.

Verifikasi TLS akhir (a)-(d) seluruhnya PASS. Baseline kedua role tetap dapat
non-TLS; role lain ditolak; app ke protected non-TLS ditolak; app verify-full ke
protected_100k berhasil. Token migrasi dicabut dan lookup token lama ditolak
403; migration_user sudah NOLOGIN, tanpa menghentikan sesi/container lain.
Tidak ada benchmark atau migrasi 1M yang dijalankan, tidak ada merge ke main.

Ukuran DB: baseline_100k **104732351 byte (99.88 MiB)**; protected_100k
**230012607 byte (219.36 MiB)**, rasio **2.196x**. Sisa disk saat pengukuran
**60.40 GiB**. Jumlah baris, OID, relfilenode, counter insert/update/delete dan
waktu start postgres/baseline_100k/baseline_1m tetap sama dengan preflight;
source ringkasan migrator juga diperiksa ulang dalam snapshot baru.

Estimasi linear 1M = 10 x durasi run penuh = **1925.62236 detik / 32.094 menit**,
sekitar 13.37% TTL empat jam, margin nominal 207.906 menit. Ini perkiraan,
bukan hasil 1M; I/O/query/validasi dapat bertumbuh nonlinier. Sebelum migrasi 1M
terpisah, terbitkan token workload baru TTL empat jam tepat sebelum mulai;
token migrasi sesi 100k sudah dicabut. Jangan menggunakan kembali token itu.

Verifikasi tambahan setelah migrasi: 15 unit test TLS + 1 integrasi scanner
read-only dengan credential baru, semuanya lulus. Raw JUnit lokal di
results/migration/, ringkasan evidence/migration/laptop-verification-tests.json.
Evidence utama lokal: laptop-completion-protected_100k.json, laptop-timings.json,
validation-protected_100k.json, laptop-preflight-protected_100k.json (COMPLETE),
evidence/infra/postgres-tls.json dan evidence/scanner/credential_rotation.json.
Evidence development Alby dan preflight lokal lama tetap tersedia di history/.
Audit literal credential/token/share/private-key dan verifier SCRAM pada 29 file
keluaran yang berubah serta log Docker PostgreSQL/OpenBao sejak bootstrap tidak
menemukan kecocokan. Evidence laptop-output-audit.json menyatakan batas scope;
ini bukan pengganti scan S06 seluruh repo/riwayat/host.

## Test atribut pada source ZIP — 28 Oktober 2026

Test export-ignore menyalin .gitattributes yang dikirim ke repository Git sementara
milik fixture. Karena itu test tetap memeriksa perilaku Git yang nyata ketika
dijalankan dari source ZIP tanpa .git/dataset panitia. Tidak menginisialisasi Git
atau mengubah atribut di checkout operator; aturan pengecualian tetap persis sama.
