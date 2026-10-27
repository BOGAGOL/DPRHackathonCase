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
