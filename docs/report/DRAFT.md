# Draf narasi laporan teknis — Tim BOGAGOL

**Draf sumber untuk review; bukan PDF final.** Basis kode 4877fc7/main 96c9edb,
29 Oktober 2026 WIB. Penulis melengkapi identitas, reviewer, caption, format sitasi,
dan hasil baru yang benar-benar mempunyai evidence. Rincian lengkap ada di
[CONTEXT.md](CONTEXT.md) dan [peta bukti](10_PETA_BUKTI.md).

## Judul kerja

**Pelindungan Data Pribadi Berbasis Assessment ketika Salinan Database Bocor:
Envelope Encryption, Pembatasan Akses dan Pengukuran Leakage pada PostgreSQL 18**

Tim BOGAGOL: Alby, Zhafif, Delf. Studi kasus sintetis panitia, bukan sistem resmi
operasional DPR RI. Persetujuan reviewer manusia: belum dicatat.

## Ringkasan eksekutif

Prototipe mengurangi pemulihan nilai sensitif dari salinan database melalui
assessment per kolom, enkripsi field terautentikasi, envelope key per record/domain,
exact search HMAC, kontrol akses dan backup streaming terenkripsi. Profile memuat
29 kolom: 21 PII dan 4 FIN dienkripsi, empat REF dipertahankan bersama age_band.
Backend membatasi scope record dan field, sedangkan analis hanya menerima agregat.

Migrasi 734/100k/1M mempunyai validasi semua field dan record sesuai lingkungan
buktinya. Pada artefak protected 100k/1M tanpa key, ESCE atas 25 kolom AEAD non-NULL
adalah 0%. REF, NULL, equality dan inferensi masih tersisa; subset sumber 734
masih mempunyai k=1. Capability FIN, PII dan search menghasilkan paparan berbeda.

Pada benchmark DB, v2 memperbaiki p95 lookup NIK protected sekitar 51% dibanding
sesi naive, tetapi keduanya masih gagal target latensi dan throughput. Error rate
0 lulus. Hasil API masih PLANNED pada snapshot. Recovery layanan nyata dibuktikan
pada lab 17 record/143 checks, web deployment 100 checks, dan guarded reset VM
memiliki bukti operator terpisah. Itu belum membuktikan DR seluruh key-plane.

## 1. Pendahuluan dan ruang lingkup

Salinan plaintext dapat mengungkap data tanpa login aplikasi. Tujuan solusi adalah
mengurangi nilai salinan tersebut, menjaga layanan sah, mengukur dampaknya, dan
menyediakan prosedur penerapan. Enkripsi tidak cukup jika aplikasi sekaligus akses
key dikuasai. Dataset dan prototipe tidak mewakili seluruh operasi instansi nyata.

PostgreSQL diizinkan soal dengan penjelasan adaptasi. Input 734 INSERT/29 kolom
tidak mempunyai DDL/PK/FK. Tim membuat schema dan surrogate id, menjaga string,
nol awal, NULL dan hubungan data. Kontribusi tim adalah menghubungkan assessment
ke profile, memisahkan domain capability, dan mengukur leakage serta tradeoff
layanan dengan evidence yang dapat ditelusuri. [B01–B04; R01 h.1]

## 2. Analisis kondisi awal dan prioritas

Jelaskan NIK-like 14 digit, regex yang dapat salah membaca rekening, anomali
tanggal, tiga nama identik dan keterkaitan alamat/keluarga. kode_bank masuk FIN
karena dapat menjadi proxy unik meskipun label acuan jenisnya non-pribadi.
Bedakan kelas hukum, risiko scanner dan domain kripto. Gunakan matriks 29 kolom
pada [tabel hasil](11_TABEL_HASIL.md), termasuk alasan dan status review manusia.
Tidak ada kolom dihapus; minimisasi tiga nama baru rekomendasi. [B01–B05]

## 3. Arsitektur dan threat model

![Arsitektur sistem](assets/architecture.png)

Browser, web/API, DB, key-plane, operator dan arsip mempunyai batas berbeda.
DB menyimpan ciphertext dan wrapped DEK. Aplikasi sah mempunyai kemampuan unwrap
dan harus menegakkan hak field. Principal RLS dapat diubah pemegang credential
app_user. Pemisahan kewenangan bukan jaminan terhadap kompromi OS/DB/Bao bersamaan.
Tabel ancaman mencakup dump, capability PII/FIN/search, tamper, IDOR dan key loss.
[B01,B15,B24]

## 4. T1 — penemuan dan assessment

Scanner menggabungkan struktur/nama/isi/pola/kamus/statistik/relasi, dengan inventory
termasking. Evaluasi 29 label mengecualikan surrogate id. Raw v1.2 precision 96,30%,
recall 100%, F1 98,11%, in-sample. Regex-only recall 42,31% walaupun precision 100%.
False positive kode_bank dan ketidakcocokan type tetap dilaporkan. Hasil satu tabel
bukan generalisasi semua instansi atau persetujuan hukum otomatis. [B02,B03]

## 5. T2 — pengurangan nilai salinan bocor

AES-256-GCM memakai nonce acak 12 byte, AAD record/kolom/versi, DEK 32 byte per
record/domain dan Transit wrap. NULL tetap NULL dan dekripsi gagal tertutup.
HMAC pada tiga kolom memberi exact lookup dengan residual equality/dictionary.
Sajikan format v1, alasan remote HMAC dan pemisahan PII/FIN. [B01,B06]

Masukkan tabel sepuluh skenario leakage dua skala dengan numerator/denominator.
No-key ESCE 0 tidak berarti metadata hilang. PII sekitar 83,67%, FIN 16,33% dan
search 12,24% sel AEAD pulih pada model capability tersebut. Ketiganya dapat
DIE 100%; FIN sendiri membawa identifier. Kamus lengkap sintetis merupakan batas
atas. Residual proyeksi 1–3 atribut populasi penuh mempunyai minimum k 136/1362,
tetapi sumber 734 tetap k=1. [B22,B23]

## 6. T3 — at rest, in transit dan in use

Field protected dan backup dilindungi, sedangkan seluruh disk/WAL/log/temp atau
instance yang masih membawa baseline plaintext tidak otomatis terlindungi.
Browser HTTPS, DB verify-full dan Bao CA/hostname memverifikasi transport.
Pengecualian baseline hanya bench/scanner dari alamat terkontrol. In use membatasi
field/DTO/scope dan app cache OFF; zeroization Python tidak dijamin. [B01,B24]

Unseal manual dua dari tiga share, token policy TTL, revokasi dan rotasi wrapper
tersedia. Rotasi lab 100.734 wrapper PII v1→v2 mempertahankan nilai field; bukan
bukti semua VM/1M telah dirotasi. DR key-plane lintas mesin tetap terbuka. [B10]

## 7. T4 — backend dan frontend

Jelaskan enam role, assignment sintetis, scope record/field, Argon2id, sesi/CSRF,
query berparameter, input strict, cookie Secure/HttpOnly/SameSite, CSP/no-store dan
audit metadata. Analis hanya analyst_summary, lima marginal dengan count>=5,
total=null dan filter cohort ditolak. Tampilkan negative tests akses tabel/view
mentah, record asing dan field finansial yang terlarang. [B11–B15]

Masking runtime B berbeda dari toolkit/contoh panitia. Jelaskan variasi itu;
jangan menyatakan semua tampilan memakai contoh yang sama atau bahwa masking
adalah enkripsi. Field yang sah dirilis memang dapat dibaca penerimanya.

## 8. T5 — metode dan hasil pengujian

### Desain eksperimen

DB 100k/1M, hardware/workload/corpus sebanding, dua sesi naive/v2 masing-masing
112 run, dua blok B-P-P-B dan empat ulangan per mode/skenario. Delapan worker,
60 detik ukur/10 detik warmup, tulisan rollback, pemeriksaan checksum/sequence,
guard AC serta resource sampling. Gunakan median per-run dan commit historis
kode yang benar-benar diukur. [B16–B21]

### Hasil

Masukkan p50/p95, throughput, error, CPU, RAM, storage dan backup/restore. Semua
skenario pada kedua skala DB gagal P01/P01A/P02, lulus P03. Contoh NIK 100k v2:
p95 B 5,4945 ms/P 37,7337 ms; throughput 2492,10/300,45 req/s. Optimasi v2 adalah
perbandingan sekunder antarsesi; jangan mengganti pasangan B/P resminya. db_time
adalah mean execution SQL per request, bukan p95 server atau biaya AES murni.
[B17,B18]

143 checks lab, 100 checks web, 31 checks SQL A5 dan 65 VM reset smoke adalah bukti
terpisah. Backup protected 100k 11,376413 s/165.999.475 byte dan restore 16,415305 s
adalah satu hasil operasional, bukan median tiga run. Backup/restore baseline 1M
aktif memakai pengganti AC 33,390723/47,396286 s; percobaan terdampak tetap disimpan.
API masih PLANNED: dua ulangan rencana kurang dari minimum tiga, GET saja dan
belum ada hasil ukur. [B09,B11–B14,B16,B20]

## 9. T6 — penerapan, operasi dan pemulihan

Ikuti assessment → TLS/key/role → migrasi baru dan validasi → akun/scope/A5 →
acceptance → cutover → backup/rotasi/retensi → evaluasi. Sertakan prasyarat,
environment privat, perintah, checkpoint/resume, rollback dan restore ke DB baru.
GCM terframe/HMAC memakai key terpisah. Tanpa Bao nilai tetap ciphertext;
dengan Bao smoke decrypt lulus, tetapi layanan perlu akun/marker/API/UI juga.
[B07–B10,B24]

Storage snapshot 1M: baseline 825.194.175 byte, protected 2.210.617.023 byte,
rasio sekitar 2,679×. Rencanakan WAL/index/raw/backup/clone/headroom; biaya produksi,
RPO/RTO dan rupiah belum tervalidasi. Custody key, certificate renewal dan purge
arsip tetap membutuhkan operator dan drill. [B08]

## 10. Keterbatasan, simpulan dan lampiran

Gunakan [batas klaim](08_KETERBATASAN_DAN_REVIEW.md) seluruhnya. Tekankan residual
REF/equality/NULL, FIN/search, principal RLS, OS/memori, scope scanner/acceptance,
kegagalan target DB/API pending, masking runtime, log/history/physical WAL dan DR.
Pemisahan kemampuan dan enkripsi mengurangi pemulihan nilai tanpa key pada scope
bukti, tetapi belum menghilangkan seluruh inferensi atau memenuhi target performa.

Gunakan [referensi](09_REFERENSI_DAN_ATRIBUSI.md), [peta bukti](10_PETA_BUKTI.md),
[tabel hasil](11_TABEL_HASIL.md), assets/, tables/ dan appendix/sbom/. Laporan tidak
memuat dump, credential, unseal key atau nilai anggota lengkap. PDF dan slide final
memerlukan review manusia serta pemeriksaan tata letak terpisah.
