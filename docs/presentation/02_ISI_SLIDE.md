# 2. Materi slide utama dan cadangan

Setiap slide mempunyai satu pesan. Teks layar berikut adalah bahan siap edit,
bukan gambar slide final. ID data K dan sumber B dipetakan pada bab5 serta
evidence_cards.json. Batas kesimpulan tidak boleh disembunyikan hanya di notes.

## S01 — Ketika salinan database bocor

**Layar:**

- Apa yang masih terbaca tanpa akses aplikasi?
- Bagaimana layanan sah tetap berjalan?
- BOGAGOL · studi kasus sintetis panitia

Visual: judul sederhana; diagram/angka belum diperlukan. Subtitle opsional
“Assessment, enkripsi field dan bukti yang dapat ditelusuri”. Jangan memakai
slogan “database mustahil bocor”. Footnote: prototipe, bukan sistem resmi DPR RI.
Transisi: “Kami mulai dari sifat datanya, sebelum memilih kontrol.”

## S02 — Risiko utama pada data

**Layar:**

- Identitas, kontak dan keuangan terbaca pada baseline
- Hubungan antaratribut membantu rekonstruksi
- REF, pola NULL dan key capability tetap berisiko

Visual: tiga kelompok risiko, disertai angka konteks **734 sumber /29 kolom**;
tanpa contoh nilai anggota lengkap. Narasi menjelaskan NIK-like14digit dan
kode_bank sebagai proxy; jangan memenuhi layar dengan matriks29 baris.
Bukti: B01–B05, K01/K02. Risiko hukum/kelas bukan identik dengan domain kripto.
Transisi: “Karena itu, perlindungan dipilih per kolom dan kebutuhan layanan.”

## S03 — Prioritas solusi dan arsitektur

**Layar:**

- Assessment→profile:25field AEAD,4 REF
- DEK per record/domain; kunci terpisah di OpenBao
- Hak minimum, TLS, exact search dan backup terenkripsi

Visual: diagram assets/architecture.svg atau versi sederhana yang tetap akurat.
Tampilkan diagram lengkap satu kali; pembicara mengikuti alur browser→API→DB/Bao,
bukan membacakan semua kotak. Bidx untuk tiga kolom, AAD mengikat record/kolom;
detail rumus menjadi A04 (cadangan). Footnote: app/v2 cache OFF; logical separation,
bukan isolasi OS jika seluruh host dikuasai. Bukti: B01/B06/B15/B24, K03/K04.
Transisi: “Kami lalu menguji salinan datanya dengan kemampuan penyerang berbeda.”

## S04 — Bukti pelindungan pada salinan data

**Layar:**

- ESCE AEAD: baseline 100%→protected tanpa key0%
- Diuji pada 100k dan1M, bukan hanya fixture
- Capability bocor dan metadata tetap menyisakan informasi

Visual utama: C01, empat bar persentase baseline/protected no-key per skala.
Footnote **wajib terlihat**: “25field AEAD non-NULL; REF/NULL/equality tidak termasuk.
Sumber 734 masih k=1.” Sebut denominator1M 24.500.005 pada notes/caption tambahan.
Jangan beri judul “0% kebocoran data”. Jika membahas FIN, tulis bahwa rekening/
NPWP/nama rekening tetap membuka identitas; capability FIN tidak membuka PII AEAD.
Bukti: B22/B23, K05/K06. Persentase capability lengkap ada pada A02 (cadangan).
Transisi: “Proteksi salinan juga harus disertai pembatasan respons layanan.”

## S05 — Akses sah dan pemulihan

**Layar:**

- Record dan field dirilis sesuai peran serta scope
- Analyst: agregat count>=5, tanpa data per record
- Backup rusak ditolak; restore diuji pada lab layanan

Visual: satu contoh alur allow/deny yang berlabel “ilustrasi”, atau evidence checks
yang telah disanitasi. Bukan screenshot UI buatan. Caption: **143 checks pada17 record
buatan tim, PG 18/Bao TLS/API/Next/Chrome**; bukti web100 checks/enam akun ditulis
terpisah bila tampil. Jangan menjumlahkannya menjadi243 record atau243 pengguna.
Versi panjang: jalankan demo4menit yang sudah disiapkan sesuai bab4. Inti5 menit:
jelaskan hasil tanpa melakukan login/restore. Bukti: B11–B15, K07/K08/K09.
Transisi: “Ada biaya yang terukur untuk menjaga proteksi ini.”

## S06 — Dampak kinerja DB

**Layar utama, contoh lookup NIK pada1M:**

- p95: baseline6,06 ms → protected38,62 ms
- Throughput:2260 →294 request/detik; error0
- Target latensi/throughput gagal; API belum terukur

Visual: C02p95 dan C03throughput terpisah; tidak satu sumbu untuk dua unit.
Caption: “DB v2,1M, median 4 run/mode;8 worker,60 s ukur,cache OFF”. Tuliskan P01/P01A/P02
**FAIL**, P03 **PASS**, bukan label hijau keseluruhan. Jangan menyebut 38 ms sebagai
latensi API/deployment. Perbaikan naive→v2 sekitar51% menjadi satu kalimat notes
atau A03 (cadangan), bukan menutupi hasil target. Bukti: B17/B18/B20/B21, K10/K11/K12.
Jika butuh konteks biaya tambahan: storage1M~2,679× pada snapshot; angkaCPU/RAM
ada di backup, bukan diubah menjadi SLA/RPO/RTO produksi.
Transisi: “Karena itu, penerapan harus bertahap dan diukur ulang.”

## S07 — Tahapan penerapan di instansi

**Layar, lima tahap:**

1. Assessment dan review klasifikasi/risiko
2. TLS, custody kunci dan role minimum
3. Migrasi target baru dan validasi seluruh data
4. Acceptance dan cutover dengan rollback
5. Backup/recovery, retensi, audit dan evaluasi

Visual: alur satu garis, lima tahap berurutan; tidak perlu dashboard/panel berlapis.
Notes: source immutable, operator/kustodian terpisah, headroom disk/token budget,
RPO/RTO/biaya instansi harus diukur. Sumber backup/key-plane berbeda; “DB pulih”
tidak sama dengan “seluruh layanan/kunci pulih”. Bukti: B07–B10/B24/B26, K13/K14.
Transisi: “Nilai solusi ini ada pada bukti dan batas yang bisa ditindaklanjuti.”

## S08 — Hasil, batas dan tindak lanjut

**Layar:**

- Nilai field AEAD tanpa key terlindungi pada scope uji
- Metadata/inferensi dan biaya performa tetap nyata
- Prioritas lanjut: API, review, audit log dan DR key-plane

Visual: teks sederhana, bukan daftar kemenangan. Tutup dengan kesiapan menjelaskan
angka/sumber dan menampilkan bukti. Tidak ada klaim produksi/patuh hukum/aman100%.
Jangan menyebut pekerjaan yang belum ada sebagai roadmap yang sudah dijalankan.

## Enam slide cadangan yang disarankan

| ID | Judul | Isi yang disiapkan | Batas tampilan |
|---|---|---|---|
| A01 | Assessment 29 kolom | Contoh struktur inventory, precision 96,30%/recall 100%/F1 98,11%, regex recall 42,31% | In-sample, review manusia belum disahkan; tanpa nilai anggota |
| A02 | Capability dan residual | ESCE PII 83,67%/FIN 16,33%/search 12,24%; DIE 100% untuk ketiganya; k sumber 734=1 | ESCE 25 AEAD, kamus search sintetis lengkap, bukan nol inferensi |
| A03 | Benchmark dan optimasi | Seluruh 7 workload pada 100k/1M, target, naive/v2, CPU/RAM/storage | DB bukan API, antarsesi bukan eksperimen kausal satu faktor |
| A04 | AAD dan envelope per record | Blob v1, AAD column/UUID/version, wrap/rewrap/bidx, cache OFF pada app | Tanpa key nyata atau dump baris; svc-app dapat kedua domain |
| A05 | Operasional dan recovery | Dua mode restore, HMAC+GCM, retensi, rotasi 100.734 wrapper, custody | DR key-plane lintas mesin/purge/secure erase belum dibuktikan |
| A06 | Evidence dan referensi | ID B/K, dataset/commit/environment,31/143/100/65 checks dipisah | Cukup rujukan aman; tidak menampilkan file privat/credential |

Jika memakai backup di deck final, masukkan ke berkas yang dikumpulkan. Backup
bukan alasan mengganti file saat presentasi. Detail penuh dapat diambil dari
tables/ dan evidence_cards.json tanpa menyalin semua JSON ke layar.
