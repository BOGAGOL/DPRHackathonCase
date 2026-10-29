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

## Reproduksi dataset besar dan simulasi kebocoran

Bagian ini merupakan runbook untuk operator, **bukan perintah yang dijalankan saat
menyiapkan submission**. Gunakan clone/workspace eksperimen baru dan instance lab
yang diotorisasi. Jangan menjalankannya pada database resmi atau menimpa evidence
beku dalam submission: CLI menulis ke path `evidence/` tetap dan tidak mempunyai
flag output bebas untuk seluruh pipeline. Simpan hasil eksperimen terpisah sebelum
membandingkannya dengan hasil tersimpan.

### Prasyarat dan environment

- PostgreSQL **18**, container **`pg-dpr`**, host **`127.0.0.1:5433`**; Python venv
  assessment dengan dependency `benchmark/requirements.txt` dan toolkit terpasang.
  Jalankan semua perintah dari root workspace eksperimen di PowerShell.
- Sumber `postgres.public.anggota` sudah diimpor operator memakai
  `sql/baseline/01_schema.sql` dan `sql/baseline/02_data.sql`, tepat **734 baris**.
  Dataset panitia dikecualikan dari `git archive` dan harus disediakan terpisah oleh
  panitia. Jangan mempublikasikannya atau mengubah sumber selama eksperimen.
- Environment yang perlu disediakan melalui pengelola kredensial privat:
  **`DATAGEN_DATABASE_URL`** (admin lab), **`BENCH_DATABASE_URL`** (`bench_user`),
  **`DPR_PRIVATE_DIR`** (folder di luar repo). Tidak ada nilai DSN/password di
  runbook ini. Generator membatasi host/port lab dan menolak overwrite target.
- Untuk provisioning, `scanner_user` sudah dibuat pemilik role. Gunakan instance
  lab terpisah bila nama `baseline_100k`/`baseline_1m` sudah ada; jangan menghapus
  database resmi agar generator dapat dijalankan.

### Dataset, validasi, dan snapshot privat

```powershell
python -m datagen --rows 100000 --seed 42 --target-db baseline_100k
python -m datagen validate --db baseline_100k --rows 100000 --seed 42
python -m datagen provision --db baseline_100k
python -m datagen snapshot --db baseline_100k --out "$env:DPR_PRIVATE_DIR\baseline_100k.dump"

python -m datagen --rows 1000000 --seed 42 --target-db baseline_1m
python -m datagen validate --db baseline_1m --rows 1000000 --seed 42
python -m datagen provision --db baseline_1m
python -m datagen snapshot --db baseline_1m --out "$env:DPR_PRIVATE_DIR\baseline_1m.dump"
```

`--replicate-anomalies` aktif secara default: 734 baris sumber dipisahkan dari
99.266/999.266 baris sintetis; seed 42 mempertahankan anomali secara proporsional.
`provision` memberi hak workload pada database baru, bukan tahap read-only.
Snapshot custom-format ditulis eksklusif ke file baru di luar repo. Metadata
checksum/validasi/snapshot ditulis ke `evidence/datasets/baseline_*.json` dan harus
berasal dari dataset reproduksi yang sama.

### Before: known-values, dump plaintext, dan leakage budget

```powershell
python -m verify.leak_sim --scenario baseline_dump --db baseline_1m --artifact "$env:DPR_PRIVATE_DIR\baseline_1m.dump" --known-values "$env:DPR_PRIVATE_DIR\verify\baseline_1m.sqlite"
python -m verify.leakage_budget --known-values "$env:DPR_PRIVATE_DIR\verify\baseline_1m.sqlite" --leak evidence/leak/baseline_dump.json --residual evidence/leakage/residual_before.json
```

Jika ledger belum ada, `baseline_dump` membuat known-values SQLite dari pembacaan
baseline yang read-only melalui `BENCH_DATABASE_URL`. Ledger berisi nilai mentah
dan kunci pencocokan HMAC privat, tidak boleh di-commit. Pencocokan memakai hash/set
baris dan lookup batch berindeks; checksum harus cocok dengan dataset dan snapshot.
Hasil: `evidence/leak/baseline_dump.json`, `evidence/leakage/baseline_dump.json`,
`residual_before.json`, dan tabel before pada `evidence/leakage/before_after.csv`.
CLI baseline ini khusus **1M**; jangan mengganti `--db` menjadi `baseline_100k`
karena pilihan tersebut tidak didukung.

### After tanpa kunci

Prasyarat tambahan: migrasi Modul A sudah tervalidasi ke `protected_1m` pada lab
eksperimen yang sama, profile `policy/protection_profile.yaml` cocok, dan operator
sudah menyiapkan **dump custom-format** `protected_1m.dump` di `DPR_PRIVATE_DIR`.
Runbook ini tidak melakukan migrasi atau restore. Ekspansi dump memakai
`pg_restore --file=-` melalui container, tidak memulihkannya ke database.

```powershell
Remove-Item Env:DPR_LEAK_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:OPENBAO_TOKEN -ErrorAction SilentlyContinue
python -m verify.leak_sim --scenario protected_dump_no_key --db protected_1m --artifact "$env:DPR_PRIVATE_DIR\protected_1m.dump" --known-values "$env:DPR_PRIVATE_DIR\verify\baseline_1m.sqlite"
```

`protected_dump_no_key` tidak membaca token atau membuat klien OpenBao; hanya
memproses dump dan ledger privat. PostgreSQL container tetap diperlukan sebagai
alat `pg_restore`, tetapi tidak ada koneksi DB untuk dekripsi. Hasil budget ada di
`evidence/leakage/protected_1m/protected_dump_no_key.json`, salinannya di
`evidence/leak/protected_1m/`, serta `residual_after.json` untuk REF + `age_band`.

### After dengan kemampuan kunci yang dibatasi

**Operasi operator terpisah:** sediakan `DPR_SECRETS_DIR`, `OPENBAO_ADDR`,
`OPENBAO_CACERT`, dan sementara `OPENBAO_TOKEN` dari penyimpanan privat. Perintah
berikut membuat/memverifikasi tiga policy simulasi dan menerbitkan token terisolasi,
bukan token `svc-app`. Token bootstrap root hanya untuk operator; jangan diteruskan
ke worker. TLS tetap diverifikasi dan tidak ada ekspor KEK atau search key.

```powershell
python -m verify.attacker_setup
Remove-Item Env:OPENBAO_TOKEN -ErrorAction SilentlyContinue
```

Policy **`modc-leak-pii`**, **`modc-leak-finance`**, dan **`modc-leak-search`**
masing-masing dibatasi unwrap PII, unwrap FIN, atau oracle HMAC search. Token orphan,
tidak renewable, TTL dan explicit max TTL **14.400 detik**. Respons token disimpan
di **`DPR_SECRETS_DIR/openbao/tokens/<policy>-<timestamp>.json`**, di luar repo.

Operator memuat **`DPR_LEAK_TOKEN`** dari respons policy yang sesuai menggunakan
pengelola rahasia, tanpa mencetak nilainya. Jalankan setiap worker dengan **hanya
satu** token yang cocok, lalu hapus variabel itu sebelum memilih token berikutnya:

```powershell
# Muat DPR_LEAK_TOKEN milik modc-leak-pii secara privat sebelum perintah ini.
python -m verify.leak_sim --scenario protected_dump_with_pii_key --db protected_1m --artifact "$env:DPR_PRIVATE_DIR\protected_1m.dump" --known-values "$env:DPR_PRIVATE_DIR\verify\baseline_1m.sqlite"
Remove-Item Env:DPR_LEAK_TOKEN -ErrorAction SilentlyContinue

# Muat DPR_LEAK_TOKEN milik modc-leak-finance secara privat.
python -m verify.leak_sim --scenario protected_dump_with_finance_key --db protected_1m --artifact "$env:DPR_PRIVATE_DIR\protected_1m.dump" --known-values "$env:DPR_PRIVATE_DIR\verify\baseline_1m.sqlite"
Remove-Item Env:DPR_LEAK_TOKEN -ErrorAction SilentlyContinue

# Muat DPR_LEAK_TOKEN milik modc-leak-search secara privat.
python -m verify.leak_sim --scenario protected_dump_with_search_key --db protected_1m --artifact "$env:DPR_PRIVATE_DIR\protected_1m.dump" --known-values "$env:DPR_PRIVATE_DIR\verify\baseline_1m.sqlite"
Remove-Item Env:DPR_LEAK_TOKEN -ErrorAction SilentlyContinue
```

Worker memeriksa nama policy dan batas TTL; token salah/kedaluwarsa gagal tertutup.
Eksperimen search memakai seluruh known-values pada tiga kolom terindeks sebagai
dictionary yang sengaja sangat kuat. Hasilnya merupakan batas atas eksperimen ini,
bukan asumsi bahwa penyerang nyata mengetahui seluruh nilai sumber.

### Leakage budget after dan perbandingan

Keempat worker protected **langsung menghitung** ESCE, DIE, ELS, dan DBR; tidak ada
flag `--after` pada `verify.leakage_budget`. Budget after disimpan per skenario di
`evidence/leakage/protected_1m/`. Jangan menjalankan ulang CLI before setelah after
untuk membuat gabungan karena itu menulis ulang tabel before.

Untuk membandingkan **hanya 1M yang baru direproduksi**, kode berikut membaca JSON
hasil run baru dan menulis CSV baru dengan fungsi pembanding yang sama. Tidak
memerlukan data mentah, token, DB, atau OpenBao:

```powershell
@'
import csv, json
from pathlib import Path
from verify.after_comparison import comparison_rows, SCENARIOS
folder = Path("evidence/leakage")
read = lambda path: json.loads(path.read_text(encoding="utf-8"))
before = read(folder / "baseline_dump.json")
before_residual = read(folder / "residual_before.json")
after_residual = read(folder / "protected_1m/residual_after.json")
assert before["status"] == after_residual["status"] == "PASSED"
rows = []
for scenario in SCENARIOS:
    after = read(folder / "protected_1m" / (scenario + ".json"))
    assert after["status"] == "PASSED"
    rows.extend(comparison_rows(before, after, before_residual, after_residual))
with (folder / "before_after_reproduced_1m.csv").open("x", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
'@ | python -
```

Agregator `python -m verify.after_comparison` tidak menerima flag dan membutuhkan
**kedua skala 100k dan 1M**, lengkap dengan before/residual/empat after yang baru dan
sesuai. Jalankan hanya jika semua prasyarat itu direproduksi; jangan mencampurkan
100k historis dengan 1M baru. Pipeline before 100k tidak disediakan oleh CLI
`verify.leak_sim` ini. Hasil gabungan tersimpan pada
[evidence/leakage/before_after.csv](../evidence/leakage/before_after.csv).

### Acuan hasil dan durasi

Untuk dataset 1M, `population=all`, penyebut ESCE **24.500.005 sel sensitif
non-NULL** pada 25 kolom kontrak; bukan seluruh sel database:

| Skenario | Sel pulih persis | ESCE |
|---|---:|---:|
| `protected_dump_no_key` | 0 | 0 |
| `protected_dump_with_pii_key` | 20.500.005 | 0,8367 |
| `protected_dump_with_finance_key` | 4.000.000 | 0,1633 |
| `protected_dump_with_search_key` | 3.000.000 | 0,1224 |

Rujukan: [before/after](../evidence/leakage/before_after.csv). Hitung ulang penyebut
dari ledger eksperimen bila sumber/profil berubah. REF, pola NULL, metadata,
kesetaraan blind index, dan inferensi turunan tetap di luar klaim ESCE nol.

[Eksekusi dataset 1M tersimpan](../evidence/datasets/baseline_1m_execution.json)
mencatat **300,12 detik** pipeline total, termasuk generate/validasi, validasi
terpisah, dan snapshot; generate dengan validasi sekitar **182,88 detik** dan
snapshot **25,13 detik**. Ini acuan laptop lab, bukan SLA dan bukan durasi migrasi
atau seluruh simulasi protected. Oracle Transit pada jutaan sel dapat jauh lebih
lama; pastikan TTL token mencukupi dan jangan mengulang otomatis bila gagal.
