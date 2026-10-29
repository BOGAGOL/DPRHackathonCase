# Metodologi pengujian

## Tujuan dan batas

Pengujian dibedakan menjadi unit/regresi, acceptance service nyata, simulasi salinan
bocor, pemulihan, dan kinerja. Jumlah test antar-suite yang bertumpang tindih tidak
dijumlahkan sebagai kasus unik. PASS berlaku pada scope dataset/lingkungan yang
dicatat; skip/NOT_RUN dan setup gagal tidak menjadi keberhasilan.

## Dataset dan assessment

Sumber 734 record mempunyai 29 atribut, tanpa DDL/PK dari dump; DDL baseline menjaga
identifier sebagai teks agar nol awal utuh. Anomali sumber tidak dikoreksi diam-diam.
Datagen menggunakan seed 42: 100k=734+99.266 sintetis;1M=734+999.266 sintetis.
Sumber/baseline dipertahankan; generator menolak overwrite target existing.

Scanner membaca snapshot read-only, menggabungkan isi/nama/pola/relasi, menulis contoh
termasking dan statistik. Evaluasi dibandingkan acuan29 kolom (in-sample). Protection
profile dibangun dari inventaris + override kontrak; klasifikasi acuan berbeda dari
keputusan enkripsi bila risiko gabungan/keunikan memerlukan perlindungan tambahan.

## Acceptance 734 record

`python -m infra.reproduce verify --data <02_data.sql>` membuat service baru dengan
TLS, mengimpor734, menjalankan assessment, membangun profile run, migrasi, validasi
seluruh field, run ulang untuk idempotensi dan pencabutan token migrasi. Enam akun
baru diuji menggunakan Chrome setelah backup/restore. Pengujian mencakup akses
record/field, raw JSON, analytics, cookie/storage, TLS, tamper dan retention.

Hasil manusia: report.html. Hasil mesin: summary.json, migration.json, security.json,
browser.json, restore/tamper/retention.json di evidence/reproduction/<run-id>.
Frontend unit dengan mock bukan pengganti service nyata. Deployment publik merupakan
lingkungan berbeda; pemeriksaan login200/TLS bukan acceptance enam akun ulang.

## Simulasi kebocoran

`python -m verify.leak_sim --help` menampilkan skenario baseline, protected tanpa
kunci, serta dengan kemampuan PII/FIN/search. Known-values/matching key dan dump hanya
berada di penyimpanan privat. ESCE = nilai sensitif non-NULL yang pulih persis /
total sel sensitif non-NULL. DIE menghitung record dengan identifier langsung pulih.
ELS membahas equality/frequency; REF/NULL/ukuran tetap bocor. Penyebut tidak dicampur
antara 734/100k/1M atau field AEAD dengan seluruh database.

## Benchmark besar (terpisah dari demo)

```powershell
python -m venv .venv-benchmark
.venv-benchmark/Scripts/python -m pip install -r benchmark/requirements.txt -e toolkit
.venv-benchmark/Scripts/python -m datagen --help
.venv-benchmark/Scripts/python -m benchmark --help
.venv-benchmark/Scripts/python -m benchmark.api --help
```

Linux memakai bin/python. Berikan DSN melalui env privat: DATAGEN_DATABASE_URL untuk
operator generator, BENCH_DATABASE_URL untuk bench_user. Jangan menulis password
literal pada command, history atau report. Jalankan datagen dengan --rows 100000 atau
--rows 1000000 dan --seed 42 pada target baru; sumber 734 harus tersedia pada instance
yang diotorisasi. Periksa bantuanCLI untuk syntax argumen dengan spasi yang benar.

Sesi DB tersimpan memakai B-P-P-B, dua blok, dua skala, tujuh workload, empat run per
mode/skenario; concurrency8, warmup10 detik, ukur60 detik, pool64, lookup set2048 seed 42,
page50. Mixed20/20/20/10/15/15; penulisan di-rollback. Laporkan median antarrun,
p50/p95, throughput, error, CPU/RAM dan ukuran. Jangan membandingkan100k dengan 1M
atau waktu DB dengan API publik. Pastikan AC/power, perangkat, dataset dan workload
sama; demo/test berat tidak berjalan selama pengukuran.

Target awal tetap pada docs/targets.md dan commit yang dicatat di metadata benchmark.
P01 p95 ratio≤1,5; toleransi absolut terpisah P01A read+5ms/write+10ms; P02 throughput≥70%
awal; P03 error tidak meningkat. Hasil DB gagal P01/P01A/P02 dan lulus P03. Naive/v2 adalah
sesi berbeda, bukan eksperimen kausal satu faktor. DEK cache OFF pada pengukuran v2.

Raw dan summary berada di evidence/benchmark/bppb_100k, bppb_1m, bppb_v2_100k,
bppb_v2_1m. Resource CPU memakai satu core sebagai 100%; CPU dapat melebihi100%.
Data tabel ringkas ada di docs/data. Replay sesi frozen memerlukan revision/source
sesuai metadata dan guard fingerprint; jangan mematikan guard untuk memaksakan run
HEAD berbeda. Seri benchmark API belum lengkap; percobaan setup bukan angka latensi.

## Penyajian hasil

`python -m verify.report` membaca catatan hasil, memeriksa tabel latency/throughput
terhadap summary asli, lalu membuat docs/RESULTS.html. Tidak ada benchmark/DB/web
request pada generator ini. Raw gagal target tetap dipertahankan; halaman tidak
menyatakan semua kewajiban atau keamanan universal telah dipenuhi.

### Command pengukuran

Dengan dataset dan credential workload/operator sudah disiapkan secara privat,
baseline awal dapat dijalankan sebagai sesi baru:

```powershell
.venv-benchmark/Scripts/python -m benchmark run --db baseline_100k --label before --adapter plain --scenario all --runs 3 --duration 60 --concurrency 8 --warmup 10
```

Runner berpasangan tersimpan pada benchmark.paired dan benchmark.paired_v2.
Untuk replay v2, siapkan checkout/env sesuai fingerprint sesi, lalu:

```powershell
.venv-benchmark/Scripts/python -m benchmark.paired_v2 preflight
.venv-benchmark/Scripts/python -m benchmark.paired_v2 run
```

Preflight harus lulus: revision/branch sesi, hash produksi/protokol, power, runtime
cache/transport, service dan tidak ada workload lain. Jangan melewati guard untuk
memaksakan pengujian pada environment yang berbeda. Output sesi existing ditolak;
pilih workspace/sesi baru dan pertahankan catatan hasil sebelumnya.

Pengukuran tidak otomatis push hasil ke Git. Publication hanya opt-in operator;
tidak diperlukan untuk membaca/menghasilkan hasil lokal. Wrapper PowerShell menerima
path launcher credential secara eksplisit, tanpa default path laptop penulis.
