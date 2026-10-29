# 6. Metodologi, hasil keamanan dan kinerja

Angka penuh dan numerator/denominator tersedia pada bab11/tables/ serta
evidence_snapshot.json. Tabel dibentuk dari hasil mesin, tidak mengetik angka
after berdasarkan estimasi. Semua hasil historis berada pada commit/lingkungan
asalnya; penyusunan konteks tidak menjalankan benchmark/migrasi baru.

## Tingkat bukti dan environment

Unit/synthetic fixture, integrasi disposable nyata, dataset development 734/100k,
laptop benchmark 100k/1M, deployment web, dan metadata operator VM adalah kelompok
berbeda. Tidak ada alasan menambahkan jumlah checks beberapa lingkungan untuk
mengklaim jumlah record yang diuji atau satu acceptance menyeluruh.

Laptop benchmark: Intel i5-1135G7 2.40GHz,8 logical CPU, RAM16.965.230.592byte,
Windows build26200, Python 3.11.3, PG 18.6 Docker postgres:18. Environment v2 mencatat
psycopg3.3.6, psutil7.2.2, HTTPX0.28.1, cryptography46.0.7, PyYAML6.0.3. Ini
bukan spesifikasi laptop Alby/VM. RAM/CPU tiap proses dipantau di run summaries.

## Assessment: gabungan versus regex

29 label sumber,26personal/3nonpersonal. Gabungan v1.2 precision 96,2963%, recall100%,
F1 98,1132%, type accuracy89,6552%, PDP-class accuracy96,5517%. Regex-only
precision 100%, recall42,3077%, F1 59,4595%. Precision tinggi regex tidak berarti
lebih baik karena banyak personal terlewat. False positive gabungan kode_bank;
ketidakcocokan type pekerjaan_terakhir/ruangan juga dicatat. Hasil in-sample,
raw_before_human_review, satu tabel. Test nama disamarkan menggunakan fixture
sintetis dan bukan held-out representatif semua instansi.

## Metode leakage dan definisi metrik

Artefak aktual COPY/dump protected diperiksa memakai batch private known-values
atau decrypt AEAD/HMAC oracle sesuai capability. Custom dump perlu pg_restore
untuk ekstraksi sebelum pemeriksaan SQL. Token simulasi dipisahkan dan dicabut;
probe ACL domain lain harus ditolak. Tidak memakai token decrypt tersembunyi pada
no-key: report menyatakan crypto_client_constructed=false.

- **ESCE** = sel sensitif non-NULL yang pulih persis / sel sensitif non-NULL yang
  diperiksa. Evidence after di sini memakai **25 field AEAD kontrak**, mengecualikan
  REF/metadata. Baseline denominator yang dibandingkan harus disebut konsisten.
- **DIE** mengukur pemulihan direct identifier pada unit/definisi evaluator yang
  dicatat; bukan proporsi nama saja. FIN dapat bernilai 100% melalui rekening/NPWP.
- **ELS** mencatat equality/frequency pada bidx dan surface yang terlihat; bukan
  jumlah dekripsi AES dan bukan bukti nol inferensi.
- **DBR** mencatat domain/kolom yang terbuka dan forbidden-decrypt probes; search
  dapat memulihkan nilai lewat kamus walaupun domains_decrypted=[] secara AEAD.

Hasil100k: denominator 2.449.994, no-key0, PII2.049.994, FIN400.000, search300.000.
Hasil1M: denominator 24.500.005, no-key0, PII20.500.005, FIN4.000.000,
search3.000.000. Persentase sekitar0 /83,6734 /16,3266 /12,2449%. Skenario
capability PII/FIN/search semuanya DIE 100%; no-key DIE 0. Baseline plaintext 100%.
Kamus search lengkap sintetis adalah batas atas yang sengaja diuji, bukan
asumsi setiap penyerang memiliki baseline lengkap. Proses terpisah bukan sandbox
OS terhadap kode yang dapat membaca seluruh storage operator.

Pernyataan yang benar: “Pada artefak dan25 field AEAD yang diperiksa, tanpa kunci
tidak ada sel non-NULL yang dipulihkan persis.” Pernyataan “data bocor sama sekali
tidak bernilai” salah karena REF/NULL/length/bidx/legacy mapping tetap terlihat.

## Residual inferensi

Verifikasi terpisah menghitung hash-counter proyeksi REF4+age_band+indikator NULL,
seluruh kombinasi1–3atribut, NULL sebagai kelompok. Indikator konstan dihilangkan
dengan alasan tidak mengubah partisi. Min-k all 100k = 136, all 1M=1362;
synthetic 135/1361. Namun subset734 asli **tetap k=1**, sampai 11 baris singleton
pada proyeksi tertentu. Repetisi sintetis menaikkan k penuh, tidak menyembuhkan
keunikan subset sumber. Jangan menulis k=136 untuk setiap kombinasi/semua record
asal atau mengubahnya menjadi klaim anonimitas universal.

A5 menutup antarmuka analis per record, bukan menghapus REF dari tabel/dump.
Scanner after yang menamai kolom ciphertext quasi_identifier dapat menghasilkan
angka k berbeda; gunakan residual terpisah yang scope atributnya eksplisit.

## Eksperimen performa DB yang sah

Tujuh operasi: read_by_nik, read_by_email, read_profile, list_page50,
update_contact, insert_member, mixed. Mixed cycle20/20/20/10/15/15. Korpus lookup
2048kunci/pagepool64, seed42, concurrency 8, warmup 10 s, measurement 60 s. Tulis
memakai id sementara dan rollback; data + sequence bisnis dicek sebelum/sesudah.
Audit setup/cleanup scope boleh append metadata dan tidak dianggap perubahan
anggota. Workload DB adapter full profile tidak selalu sama proyeksi API/UI.

Sesi **naive_v1** dan **v2** masing-masing 112 run =2skala ×2blok ×4fase B-P-P-B
×7skenario; tiap mode/skenario 4 ulangan. Median dihitung dari metrik per-run, bukan
memilih hasil terbaik atau menggabungkan semua latency lalu menganggap median
antar-run sama dengan percentile pooled. Perbandingan utama B/P di **sesi yang
sama**, bukan mengambil baseline tercepat historis dan protected sesi lain.

Baseline awal100k/1M punya3 run/skenario, sebelum pg_stat_statements dan varian
terproteksi; itu kondisi awal historis tersendiri. DB B memakai bench_user tanpa
TLS terbatas pada baseline, P memakai protected TLS; biaya transport dan crypto
termasuk hasil desain. API plain tetap DB TLS: eksperimen API harus dinilai terpisah.

### Target sebelum run

Target commit 8c09a25 mendahului sesi resmi. P01 p95P/p95B<=1,5; P01A delta
<=5ms baca/<=10ms tulis/mixed; P02 throughput P/B>=0,70; P03 median error P<=B.
P01A tambahan tidak mengganti P01. Target tidak diperlonggar setelah hasil.

**Seluruh 14 kombinasi skala×skenario pada naive maupun v2 gagal P01, P01A dan P02;
P03 lulus (error0).** Menyebut “semua test lulus” tanpa kegagalan target ini akan
menyesatkan. Contoh NIK 100k v2 p95B5,4945ms/P37,7337ms, throughput 2492,10/300,45rps;
rasio p95~6,87×, throughput~12,06%. NIK1M p95B6,064ms/P38,624ms. Lihat tabel penuh.

### Diagnosis dan optimasi

Transport lama sudah keep-alive; profiling mengindikasikan biaya dispatch/client
dan komunikasi key service. Varian v2 HTTPS pool serta HMAC batch insert memberi
p95NIK protected sekitar51% lebih rendah antarsesi dibanding naive78ms→38ms.
Ini observasi dua sesi dengan kontrol yang dicatat, bukan isolasi kausal satu
perubahan atau kelulusan target. Cache eksperimen 60 s justru memburuk; resmi OFF.

db_time adalah mean execution pg_stat_statements per request, bukan p95 server.
NIK v2 P SQL sekitar0,142ms100k/0,180ms1M versus mean client26ms. Non-DB dihitung
meanclient-meanSQL perrun, bukan p95client-p95SQL. Tidak boleh menyimpulkan
seluruh selisih hanya AES, hanya jaringan, atau hanya PythonGIL.

Resource: tiap run membawa median/peak CPU/RAM DB,client,Bao dan jumlah sampel.
CPU “percent_one_core” bisa>100%; bukan persentase kapasitas 8 core. Tabel konteks
menyajikan **median dari median per-run** dan **maksimum peak per-run** per
mode/skenario; bukan peak seluruh proses dari sampling kontinu tanpa batas.
V2 mencatat 1.585 sampel tanpa gagal koleksi. Storage snapshot dan metadata
tablespace/index/WAL harus diberi waktu, bukan angka produksi yang konstan.

### Daya, percobaan gagal dan provenance

Gangguan charger/baterai memengaruhi backup/restore1M dan crosscheck pgbench lama;
pengukuran pengganti AC diberi label, original tidak dibuang. Workload 21 run 1M
awal dinyatakan tidak terdampak/tidak diulang. Gunakan active_measurements.json:
backup1M33,390723s, restore47,396286s, dump150.429.543byte; angka23,39/27,94s
lama adalah histori terdampak, bukan hasil aktif.

V2 selesai 29 Okt 01:08:48 WIB, produksi 8a11ff7, orchestration bd5721e, evidence 6077b10.
HEAD setelah merge bukan commit yang diukur. Gate production_manifest menolak
kode/profile baru untuk replay sesi lama; gunakan checkout terisolasi historis,
jangan melemahkan gate agar laporan tampak reproducible pada HEAD berbeda.

## API: status snapshot, bukan janji hasil

api_bppb_compare.json berstatus **PLANNED**, scenarios kosong. Rencana 100k satu
blok B-P-P-B,4 GET endpoint,16 run,2 ulangan/mode/endpoint, diubah operator sebelum
measurement karena waktu. Ini di bawah minimum awal3. Update/insert/mixed API
masih di luar scope. Setup gagal/restoration dan token budget disimpan; bukan
latency run. Jangan mengisi angka API memakai DB, smoke, parity atau rencana.

## Backup, restore dan akses

Backup protected 100k 165.999.475byte,11,376413s; restore withBao16,415305s,
sample 16 record/392field non-NULL terautentikasi, HMAC+digest+frames lulus.
Ini satu evidence operasional, **bukan median3 run benchmark backup protected**.
Lab service recovery 17 record memiliki timer/ukuran sendiri dan 143 checks; jangan
menjumlahkan rows/timing dengan100k. Metadata VM golden reset 65 smoke bukan uji
key-plane disaster recovery. SQLA5 31 checks dan browser 100 checks tetap scope terpisah.

## Peta target fungsional/keamanan: status harus mengikuti cakupan

ID berikut berasal dari docs/targets.md. Kata “ada bukti” tidak berarti seluruh
persyaratan lintas lingkungan otomatis memperoleh satu PASS global.

| ID | Target awal | Bukti dan status yang dapat ditulis |
|---|---|---|
| F01 | Validasi dataset 100% | Manifest datagen 100k/1M PASSED; sumber/sintetis dipisah, seed/keunikan/relasi diperiksa |
| F02 | Semua fungsi pengguna sah benar | Test repository/role dan lab nyata ada; bukan hasil seluruh workload API terukur atau setiap record pada semua VM |
| F03 | Validasi migrasi 100% | All rows/all fields 734/100k/1M pada laporan masing-masing; bukan satu run/mesin |
| F04 | Restore berhasil | Baseline tiga run, protected dua mode dan smoke, recovery layanan lab serta reset VM punya bukti terpisah; DR key-plane penuh belum dibuktikan |
| F05 | Delete tidak muncul di backup baru | Drill record buatan pada clone lulus; backup lama tetap berisi sampai retensi berakhir |
| S01 | Semua akses ilegal wajib ditolak | Lab/VM web memeriksa role/record/field/JSON; klaim dibatasi kasus yang dijalankan |
| S02 | Role DB minimum menolak operasi ilegal | SQL A5 dan validasi ACL/RLS ada; matriks gabungan seluruh role pada setiap deployment belum menjadi satu audit final |
| S03 | ESCE AEAD no-key 0% | Terukur pada 100k/1M dengan denominator eksplisit; bukan seluruh data sensitif/metadata bernilai nol |
| S04 | Tamper/swap gagal 100% | Toolkit bit/AAD swap serta fail-closed integration diperiksa; berbeda dari replay/delete seluruh database |
| S05 | Secret aktif terdeteksi nol | Beberapa scan keluaran terbatas ada; scan seluruh repo/history/dump/backup/log final belum disatukan lengkap |
| S06 | Plaintext pribadi nol pada keluaran yang dipindai | Keluaran tertentu ditinjau; harus menyebut daftar log/temp/history/ekspor/screenshot yang benar-benar dipindai dan pengecualian persis dataset |
| S07 | Backup rusak ditolak | Tamper satu byte ditolak sebelum DB dibuat; HMAC/digest/frame juga diuji pada implementasi backup |
| S08 | Capability domain sesuai batas | PII/FIN saling ditolak, search tak mendekripsi AES; FIN/search tetap dapat mengungkap identifier |
| S09 | Kontrol aplikasi wajib lulus | Unit, lab dan browser memberi bukti sesuai scope; bukan pentest penuh atau verifikasi semua konfigurasi cloud |

Jika membuat ringkasan warna, gunakan **TERUJI PADA SCOPE**, **PARSIAL**,
**BELUM DIUJI**, dan **GAGAL TARGET**. Jangan memberi seluruh baris warna hijau
karena runner menyelesaikan proses dengan status COMPLETED.
