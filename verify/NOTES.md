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

## Langkah 5 before — metodologi dibekukan sebelum simulasi, 27 Oktober 2026

Input: snapshot datagen `baseline_1m.dump`, hash diverifikasi terhadap
`evidence/datasets/baseline_1m.json`. Known-values dibaca dari baseline_1m pada
transaksi REPEATABLE READ READ ONLY memakai bench_user, canonical full-dataset
checksum dibandingkan generation. Tidak membaca/mengubah source postgres pada
sesi ini. Seluruh 1.000.000 baris dipisahkan menjadi id<=734 (734 sumber) dan
999.266 sintetis. Ini verifikasi artefak logis; tidak menjalankan benchmark resmi.

ESCE memakai **25 kolom AEAD kontrak bagian 3** (PII 21, FIN 4), bukan label
ground truth scanner. REF jenis_kelamin, pekerjaan_terakhir, nama_kppn, nama_bank
dan surrogate id dikeluarkan; kode_bank tetap FIN. Denominator setiap populasi
adalah semua sel non-NULL di 25 kolom itu. NULL diperlakukan sebagai pola yang
terlihat, bukan sebagai plaintext berhasil didekripsi. Denominator kosong = null
ratio, tidak disimpulkan 0%. Baseline plaintext bukan kegagalan target S03 yang
memang mensyaratkan protected tanpa kunci.

DIE ditetapkan **sebelum simulasi**: nama, nama_lengkap, nama_tanpa_gelar,
nama_rekening, no_ktp, npwp, nip_kppn, rekening, email, pengguna, handphone,
telpon_jakarta, telpon_daerah. Minimal satu sel non-NULL dari daftar itu pulih
persis di record yang sama menghitung satu baris exposed. Surrogate id tidak
menambah DIE; ruangan tetap sensitif tetapi tidak masuk daftar identifier
langsung ini. Inferensi yang tidak menghasilkan nilai tepat dilaporkan terpisah,
bukan diklaim tidak mungkin.

Pencocokan efisien: known-values SQLite privat menyimpan sel asli dan HMAC key
acak 32 byte. Full-row HMAC-SHA256 (mencakup id, urutan kolom, NULL, nol awal)
dibaca sekali ke **hash set**; setiap baris COPY hanya dicocokkan sekali. Urutan
baris/kolom artefak boleh berubah. Set entries dihapus setelah match dan duplicate
id ditolak. Untuk baris berbeda, satu SELECT SQLite berindeks per batch maksimal
500 id menghasilkan set (kolom,nilai) untuk perbandingan sel tepat per record.
Tidak melakukan pencarian substring seluruh dump untuk setiap known-value,
tidak menganggap angka pendek yang kebetulan muncul di metadata sebagai exposure.
HMAC bukan enkripsi atau proteksi dataset; hanya fingerprint pencocokan privat.
Tidak mengekspor hash per nilai, key, id record atau sel asli. Partial/missing
artefak dinyatakan PARTIAL, bukan skor nol/lulus penuh.

ELS baseline: seluruh 29 kolom data plaintext membuka equality, bidx count **0**.
SQLite GROUP BY menghasilkan jumlah kelas, kelas terbesar dan histogram
`class_size -> number_of_classes`, tanpa label grup. Ini memakai ledger yang
**sudah dibuktikan cocok setiap baris** dengan artefak; bila tidak cocok, ELS penuh
tidak dihitung. Nilai NULL dikeluarkan dari histogram dan dicatat sebagai null
indicators. DBR before melaporkan dua domain yang terbuka **tanpa credential**;
belum merupakan uji token/key compromise OpenBao.

Residual k: hitung hash-counter joint dari **artefak penuh**, lalu proyeksikan
semua kombinasi 1–3 atribut REF empat + age_band + indikator NULL AEAD yang
bervariasi. Indikator konstan dicatat jumlahnya dan dikeluarkan karena tidak
memperhalus grup apa pun. Tidak memangkas kombinasi berdasarkan hasil unik;
semua hasil ada di JSON. age_band before adalah proyeksi virtual dari tanggal
lahir, usia tahun penuh terhadap 2026-10-01, kelompok 10 tahun (bukan kolom yang
sudah tersimpan baseline). Tanggal mentah baseline tetap terbuka; kombinasinya
dengan tempat_lahir/jenis_kelamin dihitung penuh secara terpisah. K sumber 734
tidak dipakai sebagai k 1M. Semua populasi, k_min, unique_rows dan denominator
ditulis, tanpa mengekspor nilai grup atau menyebut proyeksi before sebagai after.

Scanner engine v1.2 menggunakan reservoir seragam seed 42, maksimal 1.000 baris
dari stream artefak yang sama; inventory/relasi berbasis sampel, sedangkan k di
laporan berasal dari agregasi artefak penuh di atas. Ini mengadaptasi analyze/emit
yang ada, menghindari menyimpan ulang 1M JSON row di temporary SQLite scanner.
Ground truth dan evaluator tidak diubah atau dipakai untuk menentukan exposure.

Profile A belum ada di **origin/main maupun working tree** pada pemeriksaan
27 Oktober (fetch dilakukan). Format profile pada origin/feat/crypto-migration
dibaca sebagai persiapan adapter, **tidak diintegrasikan/disalin**. Adapter membaca
policy/protection_profile.yaml saat tersedia dan menolak domain/storage yang
bertentangan dengan kontrak. Skenario protected dan backup tetap BELUM DIUJI
hingga artefak serta hook toolkit/OpenBao terbatas nyata diuji. Tidak mengklaim
ESCE=0 atau DBR key dari rencana adapter. Tidak mengubah folder A, ground truth,
target, DB/source, Docker lifecycle, atau konfigurasi server pada langkah ini.

## Hasil baseline_dump 1M

Simulasi penuh selesai **256,329 detik**: export known-values 72,989 s, ekspansi
snapshot 12,656 s, matching+agregasi 100,170 s, equality budget 59,705 s, scanner
9,820 s. Snapshot generation SHA tetap sesuai; **1.000.000 full-row HMAC match**,
tanpa fallback/unknown/duplicate. Berkas SQL ekspansi sudah dihapus; snapshot
generation dan ledger privat tetap ada. Dataset/source serta hasil benchmark
resmi tidak diubah.

| Populasi | ESCE (sel non-NULL) | DIE (baris) |
|---|---:|---:|
| Semua 1M | 24.500.005 / 24.500.005 (100%) | 1.000.000 / 1.000.000 (100%) |
| Sumber 734 | 17.983 / 17.983 (100%) | 734 / 734 (100%) |
| Sintetis 999.266 | 24.482.022 / 24.482.022 (100%) | 999.266 / 999.266 (100%) |

ELS: 29 kolom plaintext dengan histogram kelas kesetaraan penuh, 0 bidx. K residual
memuat 41 kombinasi per populasi (6 atribut termasuk satu NULL indicator yang
bervariasi); 24 indikator NULL konstan dicatat. Seluruh kombinasi 1M mempunyai
0 baris unik, k_min terendah **1.362**, untuk pekerjaan_terakhir + nama_kppn +
nama_bank. Sintetis terpisah k minimum **1.361**. Sumber 734 masih mempunyai k=1;
jumlah unik tertinggi **11/734** pada pekerjaan_terakhir + nama_kppn + age_band.
Ini hanya atribut/proyeksi 1–3 yang ditentukan; tidak membuktikan anonim terhadap
semua atribut/knowledge/linkage. Angka besar 1M dipengaruhi replikasi distribusi
sintetis dan tidak menggantikan penilaian individu sumber.

Kombinasi tanggal/tempat lahir + jenis kelamin yang benar-benar plaintext before:
**730/734** sumber unik (732 grup), **3.123/1.000.000** unik pada semua baris
(167.095 grup), dan **3.136/999.266** unik pada sintetis. Ketiganya masih k=1.
Histogram dan semua kombinasi ada di residual_before.json; tabel laporan ringkas
ada di before_after.csv. Semua kolom after tetap **BELUM DIUJI**.

Hardening utilitas verifikasi: GROUP BY ledger memakai `PRAGMA temp_store=MEMORY`
agar sort key plaintext tidak ditulis ke temporary folder OS. Budget terakhir
dihitung ulang dari ledger/hasil match yang sama dengan pragma bernilai **2**
(MEMORY), tanpa query DB atau benchmark. Perhitungan awal memakai default SQLite;
temporary sort awal dikelola/dibersihkan SQLite, bukan hasil scan S06. Journal
ledger dan SQL ekspansi berada di direktori privat. Manifest kode pengukuran
awal dipertahankan di leak evidence; hash kode budget dan validasi akhir dicatat
terpisah agar perubahan utilitas tidak diklaim sudah dipakai pada tahap awal.

Audit keluaran memeriksa 12 file JSON/CSV/HTML baru, seluruh 1M known rows dan
19.196.186 sel sensitif non-NULL panjang >=6 menggunakan hash-set field equality.
Pass awal menemukan 41 kesamaan tanggal_pernikahan **hanya** terhadap field
metadata `residual_before.json:age_band.reference_date`, tanggal publik yang
dibekukan sebelum data dibuat. Audit final mengecualikan **field itu saja**;
tanggal yang sama di sample/field lain tetap akan gagal. Hasil final 0 exact
unmasked field match. Ini bukan pemeriksaan substring arbitrer/nilai pendek,
repo/log/riwayat atau kelulusan S06. Pengecualian eksplisit ada di audit JSON dan
test memastikan tidak menjadi allowlist nilai tanggal secara global.

Test memakai venv masing-masing: benchmark+datagen 55 lulus; scanner 194 lulus
(termasuk transaksi DB readonly nyata); verify 24 lulus. Pengumpulan gabungan
awal dengan venv scanner gagal karena psutil tidak ada di venv itu, lalu suite
dipisah sesuai requirements tanpa memasang/mengubah dependensi. Tidak ada test
yang menulis DB asli atau menjalankan ulang benchmark resmi.


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

## Overnight 28 Oktober 2026 — berhenti pada gerbang 0

Branch run/overnight-28okt dibuat dari fix/tls-baseline-exception (7dcdd9e).
Percobaan tunggal git merge --no-edit feat/verify-bench (fbeff98) gagal dengan
konflik content pada verify/NOTES.md. Kedua branch menambahkan bagian berbeda
pada lokasi yang sama: branch fix memuat preflight/TLS/rotasi scanner/migrasi
protected_100k; branch feature memuat metodologi dan hasil leak baseline 1M.
Tidak memilih atau menggabungkan salah satu sisi karena pengguna mewajibkan
BERHENTI bila konflik. Potongan kedua sisi disimpan dalam evidence, diff lengkap
lokal di results/overnight-28okt/gate0-merge-conflict.diff.

Working tree bersih sebelum merge. Setelah evidence konflik tersimpan,
git merge --abort mengembalikan branch run ke 7dcdd9e agar laporan kegagalan
dapat di-commit; kedua branch sumber tetap utuh. Ini membatalkan merge yang
belum selesai, bukan menyelesaikan konflik. Tidak ada retry otomatis.
Langkah 1–5 tidak dimulai: 0 token baru, 0 migrasi baru, 0 run benchmark baru,
tidak ada perubahan database, konfigurasi atau lifecycle container, dan tidak
ada merge ke main. Test aplikasi tidak dijalankan karena integrasi gagal dan
tidak ada kode yang diubah. Evidence: evidence/overnight/gate0_merge.json;
ringkasan: evidence/overnight_summary.md. Resolusi konflik dan kelanjutan
memerlukan instruksi lanjutan pengguna sesuai gerbang yang dihentikan.

## Pemeriksaan setelah charger dipasang kembali, 28 Oktober 2026

Pemeriksaan read-only menunjukkan branch run/overnight-28okt masih di f01d485,
gerbang terakhir adalah merge pada langkah 0. Merge sebelumnya sudah dibatalkan;
bukan migrasi atau benchmark yang terhenti karena baterai. Tidak ditemukan proses
Python/pgbench/pg_dump/pg_restore, tidak ada sesi DB workload terkait, database
protected_1m belum ada: **0 baris dimigrasi**, tidak ada checkpoint untuk resume.
Baseline dan protected_100k tidak diubah oleh pemeriksaan ini.

Log System / Microsoft-Windows-Kernel-Power / Event ID 105 mencatat:
AC=false **2026-10-28 00:58:21.8764242 WIB** (RecordId 27568), disusul
AC=true **00:58:54.6027659 WIB** (RecordId 27569), durasi sekitar **32.73 detik**.
Gangguan terjadi sesudah commit laporan berhenti pada 00:58:15 WIB. Tidak ada
pengukuran yang tumpang tindih: 0 run perlu ditandai terdampak baterai atau diulang.
AC saat pemeriksaan sudah true. Gangguan tetap dicatat sebagai insiden lingkungan,
bukan alasan untuk mengulang hasil terdahulu yang tidak tumpang tindih.

Evidence: evidence/overnight/ac_resume_status_20261028.json. Belum menerbitkan
token baru, membuat target, atau menjalankan workload. Pengguna dimintai keputusan
untuk melewati konflik dokumentasi verify/NOTES.md dengan mempertahankan kedua
bagian lengkap; aturan gerbang sebelumnya masih meminta berhenti saat konflik.

## Kelanjutan dengan izin union dokumentasi, 28 Oktober 2026

Pengguna mengizinkan union semua konflik dokumentasi/NOTES .md, tanpa kehilangan
isi; konflik kode/config tetap STOP. Merge feat/verify-bench diselesaikan pada
07fbf4a: prefix bersama hanya sekali, seluruh tail feature tanggal 27 Oktober,
lalu seluruh tail lokal tanggal 28 Oktober, diperiksa byte sesudah normalisasi
LF/CRLF. Tidak ada konflik kode/config. Evidence gate0_resolution.json menyimpan
hash kedua sisi dan pemeriksaan retensi lengkap; kegagalan sebelumnya diarsipkan.

Pengumpulan test gabungan awal memakai venv benchmark untuk verifier sehingga
Jinja2 tidak tersedia (dependensi dinyatakan pada verify/scanner requirements).
Tidak ada test bisnis yang dieksekusi pada collection itu. Suite selanjutnya
dipisah sesuai venv modul: benchmark/datagen 67 PASS, verify 24 PASS. Evidence
merge_verification.json tetap merekam kesalahan pemilihan lingkungan awal.

Migrasi baseline_1m -> protected_1m dimulai dengan token svc-migration dan svc-app
BARU TTL 14400 detik, tanpa root pada proses migrator. Prepare dan check PASS.
ACMonitor yang sudah diuji mengambil sampel tiap 2 detik; supervisor menghentikan
hanya child migrator miliknya jika AC tidak terkonfirmasi atau disk <10 GiB.
Checkpoint dipertahankan bila berhenti, tidak ada retry otomatis. Session.json
di evidence/overnight/migration_1m/ mencatat fase dan durasi; hasil gate 1 baru
dianggap PASS jika validation-protected_1m.json membandingkan tepat 1000000 baris.

## Hasil overnight: gerbang 1 PASS, berhenti pada gerbang 2

Migrasi protected_1m selesai: passed=true, rows_compared=1000000, complete=true,
comparison=all_rows_all_fields. Run 01:11:41.905-01:53:47.447 WIB berlangsung
2525.540631 detik (42.092 menit), termasuk validasi dan pencabutan token;
seluruh sesi token/prepare/check/run 2540.822885 detik (42.347 menit).
AC qualified: 2538 sampel, 0 sampel bukan AC, 0 Kernel-Power AC=false selama
sesi. Insiden charger 00:58:21.876-00:58:54.603 WIB berada sebelum sesi ini,
bukan run benchmark/migrasi aktif; tidak ada pengukuran yang perlu diulang.
Token migrasi dicabut dan lookup ditolak 403; migration_user kembali NOLOGIN.
Jumlah baris/OID/relfilenode/counter tulis/waktu start ketiga source tetap sama.
Ukuran dan sisa disk aktual ada di evidence/overnight/migration_1m/completion.json.

Gerbang 2 gagal pada prasyarat: benchmark/adapters/protected.py belum ada pada
branch hasil merge; hanya plaintext.py dan __init__.py yang tersedia. Pencarian
kode juga tidak menemukan ProtectedAdapter. Instrumentasi db_time di kode
diagnostik lama masih berupa usulan, bukan kolektor protected yang dapat diuji.
Tidak ada permintaan parity yang dijalankan: 0 dari 1000 kunci per skenario
baca per dataset. Status read parity NOT_TESTED, db_time NOT_MEASURED;
mismatches=null, bukan nol yang diklaim lulus.

Sesuai instruksi gerbang, BERHENTI tanpa implementasi/perbaikan atau retry
otomatis. Langkah 3 amandemen target, langkah 4 verifikasi after, dan langkah 5
benchmark B-P-P-B belum dijalankan. Tidak mengubah ambang setelah melihat
metrik, tidak mengulang benchmark baseline, tidak merge ke main. Evidence:
evidence/benchmark/adapter_parity.json (FAILED_PRECONDITION), validasi 1M,
session/power/completion JSON, dan evidence/overnight_summary.md.
Kelanjutan memerlukan pembuatan adapter protected serta db_time dengan test
dan instruksi melanjutkan gerbang 2; pertahankan protected_1m tervalidasi.
Audit literal rahasia pada 21 file keluaran yang berubah dan log Docker PG/Bao
sejak awal sesi tidak menemukan kecocokan credential/token/share/private-key
aktif. Scope terbatas ini tercatat di evidence/overnight/output_audit.json;
tidak menggantikan verifikasi after atau scan S06 yang belum dijalankan.
