# Konteks lengkap persiapan presentasi — BOGAGOL

Paket persiapan 29 Oktober 2026 WIB; bukan deck final atau operasi demo baru.

# 1. Brief, fokus dan alur presentasi

## Tujuan dan posisi solusi

Judul kerja: **Pelindungan Data Pribadi ketika Salinan Database Bocor**.
Tim BOGAGOL: Alby (infra/kripto/migrasi/backup), Zhafif (aplikasi/akses/deployment),
Delf (scanner/datagen/benchmark/leakage). Studi kasus sintetis panitia; bukan
aplikasi operasional resmi DPR RI atau sistem produksi tersertifikasi.

Pertanyaan pembuka: jika salinan database dikuasai pihak tidak berwenang,
informasi apa yang masih terbaca dan apakah layanan sah tetap bekerja?
Tujuan presentasi adalah menjelaskan keputusan dan buktinya, termasuk tradeoff.
Tiga kontribusi: assessment mengendalikan profile, simulasi leakage dengan
capability berbeda, dan pemisahan domain kripto per record.

## Lima pokok soal dan lokasi dalam deck

| Pokok yang harus dipaparkan | Slide utama | Pesan yang harus sampai |
|---|---|---|
| Risiko utama | S01–S02, S08 | Identitas/keuangan mudah terbaca pada baseline; relasi, REF/NULL dan key capability tetap penting |
| Prioritas solusi | S03 | Assessment→profile;25 AEAD/4 REF; DEK per record/domain; akses/TLS/backup lebih dahulu |
| Bukti pelindungan | S04–S05 | Hasil no-key/capability, negative akses, A5, restore; sebut numerator/denominator dan lingkungan |
| Dampak kinerja | S06 | Data DB nyata, target gagal dan error lulus; API belum ada hasil; resource/storage punya biaya |
| Tahapan instansi | S07–S08 | Assessment, fondasi, migrasi baru, validasi/cutover, operasi/recovery; owner dan gap jelas |

## Waktu: inti lima menit dan versi panjang

| ID | Pokok slide | Inti detik | Versi panjang detik |
|---|---|---:|---:|
| S01 | Pertanyaan dan batas studi kasus |20|35|
| S02 | Risiko utama dan assessment |40|65|
| S03 | Prioritas solusi dan arsitektur |50|90|
| S04 | Bukti dump/leakage |50|100|
| S05 | Akses dan pemulihan, demo opsional |45|300 termasuk 240 detik demo|
| S06 | Dampak kinerja |45|120|
| S07 | Tahapan penerapan |35|85|
| S08 | Hasil, batas dan tindak lanjut |15|45|
| Total | |**300**|**840**|

Versi panjang14 menit menyisakan60 detik untuk transisi/gangguan sehingga tetap
dalam15 menit. Demo termasuk waktu S05, jangan ditambahkan lagi sesudah840 detik.
Jika hanya mendapat lima menit, gunakan delapan slide dan evidence ringkas,
tanpa login/terminal/live restore. Q&A maksimum10 menit di luar presentasi sesuai
soal final. Slide backup dibuka saat Q&A/ditukar ke alur hanya setelah menghitung
ulang waktu; bukan menambah presentasi melewati batas.

Disarankan satu narator untuk inti lima menit agar transisi tidak memakan waktu.
Pada versi panjang, tim dapat membagi Alby S03–S05, Delf S02/S04/S06 dan Zhafif
demo/aplikasi. Itu usulan pembagian, bukan assignment yang sudah disetujui.

## Sumber ketentuan

Soal final bertanda tangan R01,4halaman: halaman4 meminta lima pokok di atas,
presentasi 31 Oktober 2026 maksimal15 menit termasuk demo, Q&A10 menit. Dokumen detail
R02,8halaman: halaman7 memuat presentasi inti 5 menit; halaman8 mewajibkan berkas
yang dikumpulkan sama dengan yang dipresentasikan. Kedua dokumen telah diperiksa
pada tugas laporan; identitas/hash tercatat pada source_manifest.json paket ini.

R01 memperbolehkan PostgreSQL dengan adaptasi dump. Prototipe tidak dituntut
setara produk operasi, tetapi klaim harus punya bukti. Final deck sebaiknya sudah
memuat backup slides yang diperlukan; jangan mengedit file sesudah pengumpulan
lalu menganggapnya identik. Konfirmasi rundown terbaru ke panitia secara manual.

---

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

---

# 3. Naskah pembicara

Naskah inti berikut ditujukan untuk sekitar lima menit bersama jeda dan perpindahan
slide. Ini **belum latihan waktu oleh pembicara manusia**. Pertahankan makna angka,
scope, dan hasil gagal ketika memendekkan kalimat. Jangan membaca caption sumber
panjang keras-keras; caption tetap terlihat untuk juri.

## S01 — 20 detik

“Kami Tim BOGAGOL. Pertanyaan kami adalah: ketika salinan database bocor, apa yang
masih dapat dibaca, dan apakah layanan sah tetap bekerja? Kami menguji prototipe
pada data sintetis panitia. Tujuannya mengurangi nilai salinan bocor, dengan bukti
yang dapat diperiksa dan batas yang dinyatakan.”

## S02 — 40 detik

“Sumber berisi 734 record dan 29 kolom. Risikonya mencakup identitas, kontak dan
keuangan, tetapi tidak berhenti pada nama kolom. Identifier KTP-like justru
14 digit, sehingga regex 16 digit dapat salah sasaran. Hubungan antarnama,
alamat, dan kode institusi juga membantu rekonstruksi. Kami melakukan assessment
sebelum memilih kontrol. Metadata, pola NULL dan kemampuan akses kunci tetap
menjadi bagian risiko setelah enkripsi.”

## S03 — 50 detik

“Assessment dan override tim membentuk profile perlindungan. Dua puluh lima field
memakai AES-GCM, sedangkan empat atribut referensi dipertahankan untuk kebutuhan
layanan. Setiap record mempunyai DEK terpisah untuk domain PII dan finansial,
dibungkus oleh OpenBao. AAD mengikat ciphertext ke record dan kolom sehingga
pertukaran tidak diterima. Tiga blind index memberi pencarian exact, dengan
kebocoran equality yang kami akui. Prioritas berikutnya adalah TLS, hak minimum,
pembatasan respons dan backup terenkripsi. Pemisahan ini berbasis kewenangan;
kompromi aplikasi bersama akses kunci tetap dapat membuka data.”

## S04 — 50 detik

“Kami menguji salinan data nyata pada 100 ribu dan satu juta record. Pada 25 field
AEAD non-NULL yang diperiksa, baseline pulih seratus persen, sedangkan protected
tanpa kunci nol persen. Ini bukan nol seluruh informasi: REF, panjang, pola NULL
dan equality masih terlihat. Saat capability PII, finansial atau search ikut
bocor, hasilnya berubah dan diukur terpisah. Capability finansial tidak membuka
PII AEAD, tetapi rekening dan NPWP tetap identifier. Subset sumber 734 juga masih
memiliki k sama dengan satu; pembesaran sintetis tidak membuatnya otomatis anonim.”

## S05 — 45 detik

“Layanan membatasi record dan field sebelum respons dikirim. Anggota hanya data
miliknya; analis tidak mendapat tabel atau view per record, melainkan lima
marginal dengan count minimal lima. Kelompok kecil tidak mengeluarkan label.
Kami mempunyai 143 pemeriksaan lab nyata pada 17 record buatan tim, termasuk
restore, TLS, API dan Chrome. Bukti web deployment seratus pemeriksaan enam akun
adalah pengujian terpisah. Backup yang diubah ditolak; pemulihan dengan kunci dan
tanpa kunci mempunyai arti berbeda. Bukti ini tidak kami sebut DR seluruh server.”

## S06 — 45 detik

“Biaya pelindungan cukup besar. Contoh lookup NIK pada satu juta record, median
empat run per mode: p95 baseline 6,06 milidetik menjadi 38,62 milidetik protected.
Throughput turun dari sekitar 2260 menjadi 294 request per detik, error tetap nol.
Target latensi dan throughput gagal, sedangkan target error lulus. Optimasi
transport memperbaiki hasil dibanding sesi naive, tetapi tidak menghapus
kegagalan target. Ini benchmark DB, bukan latensi API. Hasil API pada snapshot
masih belum tersedia dan tidak kami isi menggunakan angka DB.”

## S07 — 35 detik

“Untuk instansi, kami menyarankan lima tahap: assessment dengan review manusia;
TLS, custody kunci dan role minimum; migrasi ke target baru dengan validasi;
acceptance dan cutover yang mempunyai rollback; lalu backup, recovery, retensi,
audit dan evaluasi. Sumber tetap dijaga. DB, layanan dan key-plane memerlukan
prosedur pemulihan berbeda. Resource, biaya, RPO dan RTO harus diukur lagi pada
beban serta topologi instansi, bukan dijanjikan dari hasil laptop.”

## S08 — 15 detik

“Hasilnya adalah pengurangan pemulihan field sensitif yang terukur, disertai fungsi
dan pemulihan pada scope uji. Metadata dan biaya performa tetap nyata. Prioritas
lanjut kami adalah benchmark API, review, audit log dan DR key-plane. Terima kasih.”

## Tambahan untuk versi panjang

| Slide | Tambahan yang dapat dijelaskan | Jangan dilakukan |
|---|---|---|
| S01 | Bedakan mencegah kebocoran dan mengurangi nilai salinan yang sudah bocor | Mengklaim database tidak mungkin dicuri |
| S02 | Contoh kode_bank sebagai proxy, tiga nama identik, review label dan hasil scanner in-sample | Menampilkan nilai lengkap sumber atau menganggap semua kelas hukum telah disahkan |
| S03 | Alur satu request, DEK/wrapper, field minimum, svc-app dapat kedua domain, cache OFF | Menampilkan key/token, mengatakan Bao mengetahui role HTTP pengguna |
| S04 | Numerator/denominator, FIN/search dictionary, REF/NULL dan k sumber | Menyebut 0% semua leakage atau FIN sama sekali tidak mengungkap identitas |
| S05 | Maksimal60 detik pengantar + demo240 detik | Menjalankan migrasi/rotate/restore pada database benchmark live |
| S06 | Dua blok B-P-P-B, empat ulangan, target sebelum run, naive/v2, resource/storage | Membandingkan baseline sesi lain seolah pasangan utama atau menyebut p95 server dari mean SQL |
| S07 | Owner DBA/kustodian/operator, headroom, retensi, rollback dan kehilangan kunci | Membuat SLA, biaya rupiah atau keberhasilan DR yang belum diukur |
| S08 | Ringkas kekuatan/batas dan penanggung jawab pekerjaan lanjut | Mengakhiri dengan klaim semua persyaratan lulus |

Versi panjang memiliki840 detik termasuk demo, ditambah60 detik buffer. Latih
peralihan pembicara di dalam alokasi slide. Jika timer melewati batas, kurangi
detail cadangan; kelima pokok inti dan batas kesimpulan tetap disampaikan.

---

# 4. Demo, privasi dan skenario cadangan

**Status: rencana demo, bukan sesi demo yang sudah direkam/dijalankan pada tugas ini.**
Tidak ada akun, password, cookie, key, token, alamat credential atau isi record
yang disimpan dalam paket presentasi. Deployment yang pernah diuji tidak otomatis
berarti siap untuk ditampilkan sekarang tanpa preflight operator.

## Ruang demo dan batas izin

Pilihan yang paling mudah dikendalikan adalah lab/clone khusus dengan record
sintetis **buatan tim sendiri**, akun scope yang disiapkan, dan TLS yang sah.
Evidence lab17 record sudah ada; itu bukan pernyataan proses lab masih hidup.
Operator perlu menyiapkan ulang lingkungan terisolasi sebelum presentasi.

Jika memakai VM existing protected_734, dataset panitia tetap mempunyai batas
publikasi. Jangan membuka detail yang mengirim nama/identifier/keuangan lengkap.
Pilih agregat/hasil termasking yang telah direview. Finance memang mendapat nilai
FIN lengkap menurut hak; jangan menampilkan responsnya ke proyektor hanya karena
akun sah. Operator detail membuka nama, sehingga jangan menganggap semua detail
otomatis aman. Perbedaan masking runtime/toolkit tetap berlaku.

Tidak ada reset/provisioning, insert/delete anggota, migrasi, key rotation,
unseal, revokasi token atau restore berat pada database existing saat demo.
Login/logout normal tetap menulis metadata sesi/audit; “read-only anggota” bukan
tidak ada perubahan metadata sama sekali. Jangan mengakses laptop benchmark Delf.

## Rundown240 detik di dalam S05

| Detik | Aksi yang disiapkan | Hasil yang harus tampak | Cadangan bila tidak siap |
|---|---|---|---|
| 0–15 | Buka browser/demo yang sudah preflight | HTTPS sah, layar bersih tanpa terminal/env/credential | Jelaskan ini akan memakai evidence tersimpan |
| 15–50 | Operator membuka daftar, bukan detail berisi sumber lengkap | Nama termasking, respons sesuai allowlist | Ilustrasi berlabel atau screenshot fixture yang benar-benar direkam dan direview |
| 50–90 | Akun anggota fixture sendiri vs record fixture lain | Record sendiri sah, record asing ditolak, tanpa membuka identitas sumber | Tunjukkan nama checks terkait pada laporan lab, bukan response anggota |
| 90–150 | Analyst membuka summary/filter marginal | count>=5, total=null, tanpa baris per record; cohort filter ditolak | Bukti SQL A5 dan lab nyata yang sudah ada |
| 150–220 | Buka ringkasan restore/tamper yang sudah disanitasi | Backup rusak ditolak; dua mode restore dan scope lab dijelaskan | Slide S05 dengan kutipan evidence, berlabel “hasil pengujian sebelumnya” |
| 220–240 | Logout dan kembali ke presentasi | Sesi berakhir, tidak ada secret di layar | Tutup demo, lanjut S06 |

Jangan membuka developer tools bagian headers/cookies atau shell yang pernah
memuat environment privat. Jika ingin menunjukkan raw JSON, gunakan fixture dan
respons allowlist yang direview terlebih dahulu; jangan memperlihatkan request
header atau network trace mentah. Jangan memakai browser dengan password manager,
autofill, notifikasi pribadi atau akun lain yang terlihat.

## Preflight operator sebelum hari presentasi

1. Tentukan lingkungan dan pemiliknya; verifikasi tidak ada benchmark aktif dan
   tidak akan menyentuh sumber panitia atau instance anggota lain.
2. Siapkan fixture, record assignment, akun dan hak yang tepat lewat prosedur
   berizin. Langkah setup bukan bagian live demo dan tidak dilakukan tugas ini.
3. Periksa initialized/unsealed Bao tanpa membuka recovery material; CA/hostname
   TLS benar, token memiliki TTL cukup, service siap dan app cache OFF.
4. Periksa scope/field/A5 pada kode yang benar-benar terpasang. Catat commit dan
   waktu secara privat/metadata aman; jangan menganggap metadata lab lama sebagai
   bukti setiap konfigurasi VM sekarang.
5. Latih semua langkah, urutan akun, logout, dan waktu. Login dilakukan privat
   sebelum proyeksi bila memungkinkan; tidak menaruh akun/password di slide/notes.
6. Rekam cadangan hanya setelah persetujuan tim dan review setiap frame serta
   audio/metadata. **Video/screenshot belum dibuat oleh paket ini.**
7. Siapkan laporan checks lokal dan deck agar demo tetap dapat dijelaskan tanpa
   internet. Labeli rekaman/evidence sebagai rekaman/hasil sebelumnya.

## Aturan gagal yang sederhana

Jika readiness/TLS/token/akun gagal, jangan mematikan verifikasi TLS, memberi
superuser, mengulang init atau mengganti root token. Setelah satu percobaan
singkat, gunakan evidence yang telah direview. Sisihkan sisa waktu untuk dampak
kinerja dan penerapan. Kesalahan diakui sesuai scope; tidak memalsukan UI sukses.

Kalimat fallback: “Layanan demo saat ini tidak siap, jadi kami menunjukkan hasil
pengujian sebelumnya. Bukti ini berasal dari lab17 record dengan PG 18/OpenBao TLS,
bukan operasi live barusan. Berikut pemeriksaan akses dan restore yang tercatat.”

## Yang dapat ditampilkan dari evidence

- SQL A5: analyst ditolak membaca raw table/view dan kelompok1–4 tidak dirilis.
- Lab 143 checks: record/field, HTTPS/TLS negative, API/Chrome dan recovery pada17 fixture.
- Web 100 checks: enam akun existing, scope web read-only anggota; tanpa SSH Alby.
- Operator VM: satu guarded reset dan65 smoke; bukan full pentest atau DR key-plane.
- Backup tamper: satu byte diubah pada salinan uji lalu restore ditolak sebelum
  DB dibuat; jangan mengubah arsip operasional hanya untuk demonstrasi.

Masing-masing bukti mempunyai waktu/lingkungan sendiri. Menampilkan laporan bukan
berarti menjalankan ulang test, dan bukan alasan mengekspor source dataset ke slide.

---

# 5. Angka, bukti dan spesifikasi visual

## Sumber fakta

Basis penulisan adalah konteks laporan/evidence yang sudah disiapkan pada branch
submission, bukan angka hasil benchmark baru. Snapshot laporan memuat hasil kode
dan sesi historis berbeda. source_manifest.json mengikat sumber paket presentasi;
commit paket bukan otomatis commit kode yang diukur pada eksperimen.

| ID | Angka/fakta yang dapat dipakai | Sumber dan batas |
|---|---|---|
| K01 | Sumber 734 record/29 kolom, target 100k/1M | Kontrak/profile/validation; data panitia sintetis, tidak ada nilai lengkap di slide |
| K02 | Scanner precision 96,30%, recall 100%, F1 98,11%; regex recall 42,31% | B03;29 label, in-sample, raw sebelum pengesahan manusia |
| K03 |21 PII+4 FIN=25 AEAD;4 REF;3 bidx | B01/B05; field counter bukan jumlah seluruh kolom DB |
| K04 | AES-256-GCM, nonce 12 byte, DEK 32 byte/record/domain, AAD | B01/B06; format v1, fail closed, bukan seluruh disk/WAL |
| K05 | No-key ESCE 0% pada 100k/1M | B22; denominator 2.449.994/24.500.005 sel AEAD non-NULL |
| K06 | PII~83,67%, FIN~16,33%, search~12,24%; k sumber 734=1 | B22/B23; FIN/search dapat identifier, kamus lengkap sintetis, proyeksi residual 1–3 atribut |
| K07 | SQLA5 31 checks, ambang 5 | B11; fixture SQL terisolasi, bukan semua VM |
| K08 |143 checks/17 record buatan tim | B12; layanan+restore+TLS+Chrome nyata, bukan benchmark dataset |
| K09 |100 checks/enam akun web; operator VM reset 65 smoke terpisah | B13/B14; bukan 243 checks satu lingkungan, bukan full pentest |
| K10 | DB v2 NIK 1M p95 B 6,0637/P 38,6237 ms; throughput 2260,0568/293,6117 rps | B18; median 4 run/mode,8 worker,60 s ukur,cache OFF; P01/P01A/P02 FAIL, P03 PASS |
| K11 | Naive→v2 protected NIK 1M 78,9665→38,6237 ms (~51,09% turun) | B17/B18; antarsesi, bukan kelulusan target/isolasi sebab tunggal |
| K12 | API PLANNED, scenarios kosong | B20; rencana 2 ulangan/mode <minimum 3, GET only, tidak ada hasil ukur |
| K13 | Storage 1M 825.194.175→2.210.617.023 byte(~2,679×) | B08; snapshot, bukan ukuran konstan setelah WAL/workload berubah |
| K14 | Rotasi 100.734 wrapper PII v1 → v2; backup protected 100k 11,376413s/restore 16,415305s | B09/B10; lab Alby/operasional single result, bukan median 3 run atau rotasi seluruh 1M/VM |

Angka lengkap, scope dan locator ada di evidence_cards.json dan CSV tables/.
Sertakan minimal ID/scenario/skala/unit/ulangan pada grafik, dan sumber detail di
speaker notes. Angka DB yang dipilih pada slide hanyalah contoh, bukan ringkasan
semua skenario terbaik. Semua 14 kombinasi skala×skenario pada naive/v2 gagal target
latensi/throughput, error lulus. Jangan menghilangkan hasil gagal pada footnote.

### Kode sumber B dan slide cadangan A

K01–K14 adalah kartu klaim lokal. A01–A06 adalah **slide cadangan**, sedangkan
kode B berikut diwarisi dari peta evidence laporan. Jangan menyamakan keduanya.

| Kode sumber | Arti dan locator repo |
|---|---|
| B01/B05/B06 | Kontrak/profile/kripto: docs/contracts/CONTRACT.md, policy/protection_profile.yaml, evidence/crypto/ |
| B03 | Scanner: evidence/scanner/evaluation_v1_2.json dan evaluation_regex_only.json |
| B07/B08 | Migrasi/storage: evidence/migration/validation-protected_*.json dan evidence/overnight/migration_1m/completion.json |
| B09/B10 | Backup/rotasi: evidence/backup/ dan evidence/keys/rotation.json |
| B11/B12 | SQL A5/lab recovery: evidence/access-control/analyst_suppression.json dan evidence/backup/service-recovery-integration.json |
| B13/B14/B15 | Web/VM/policy aplikasi: evidence/acceptance/deployed-browser.json, app/evidence/access-control/vm-pentest-summary.json, app/backend/service_app/ |
| B17/B18 | DB naive/v2: evidence/benchmark/bppb_compare.json dan bppb_v2_compare.json |
| B20/B21 | API/target: evidence/benchmark/api_bppb_compare.json dan docs/targets.md |
| B22/B23 | Leakage/residual: evidence/leakage/after_summary.json dan protected_{100k,1m}/residual_after.json |
| B24/B26 | TLS/runtime: infra/NOTES.md, infra/postgres/, app/deploy/ dan scripts/deploy/ |

Path ini untuk provenance, bukan instruksi membuka seluruh repo saat presentasi.
Data terpilih dan batasnya sudah berada pada evidence_cards.json; gunakan kartu K
dan CSV lokal untuk membuat grafik, lalu taruh locator sumber di notes.

## C01 — Pemulihan nilai AEAD tanpa kunci

Data: tables/chart-no-key.csv. Bar 0–100% dimulai nol, dua kelompok 100k/1M,
baseline 100 dan protected 0. Tulis denominator dalam notes; sumbu “ESCE 25 field AEAD
non-NULL (%)”. Beri label 0 agar bar nol tetap terbaca. Caption menyatakan tidak
menghitung REF/metadata/inferensi. Hindari ikon perisai “100% aman”.

## C02 — Latensi lookup NIK pada DB v2

Data: tables/chart-db-nik.csv. Dua kelompok 100k/1M, setiap kelompok baseline dan
protected. Sumbu p95 ms dimulai nol; gunakan 1M pada slide utama, dua skala di backup.
Tampilkan p95 median 4 run, bukan mean atau pooled p95. Boleh tampilkan garis target
P01 berupa 1,5× B masing-masing skala, **bukan satu batas global**. P01A terpisah.

## C03 — Throughput lookup NIK pada DB v2

Data: tabel yang sama dengan C02, kolom throughput_rps. Grafik terpisah dari
latensi karena unit/arah baik berbeda. Batas P02=70% baseline per skala. Protected
berada di bawahnya; jangan memotong sumbu sehingga penurunan tampak kecil.
Caption “DB adapter; bukan HTTP request benchmark” menjelaskan unit operasi.

## C04 — Perbaikan naive dibanding v2

Data: tables/chart-optimization.csv. Bandingkan hanya p95 protected NIK dalam
dua sesi yang dinyatakan. Tulis sekitar51% lebih rendah dan bahwa target masih
gagal; bukan “performa naik51%” tanpa metrik atau “51%lebihaman”. Koneksi lama
sudah keep-alive; perbaikan transport tidak dibuktikan hanya dari handshake.

## C05 — Capability dan residual

Data: tables/leakage.csv, ESCE 25 AEAD dalam%. Kelompok baseline/no-key/PII/FIN/search
per skala. Jangan membuat stackedbar total capability: nilai bisa overlap dan
search merekonstruksi lewat oracle, bukan AES decrypt. DIE 100% pada PII/FIN/search
harus dijelaskan bila diagram menimbulkan kesan FIN tidak mengungkap identitas.
Residual k=1source734 adalah hasil berbeda, bukan persentase ESCE.

## C06 — Biaya penyimpanan

Data: tables/chart-storage.csv, byte atau GiB dengan konversi 1024^3 yang dinyatakan.
Bandingkan skala yang sama dan beri waktu/scope snapshot. Bukan overhead murni
AES: tuple/index/metadata/wrapper ikut memengaruhi ukuran. Jangan memakai rasio
2,679× untuk meramalkan biaya produksi tanpa pengukuran baru.

## Aset dan keterbacaan

assets/ berisi diagram arsitektur PNG/SVG/Mermaid yang disalin dari bahan laporan.
Tidak ada logo resmi, foto dekoratif, screenshot aplikasi atau video yang dibuat
pada tugas konteks ini. Jika deck dibuat, diagram/grafik harus tetap tajam dan
bisa diedit bila relevan. Gunakan satu komposisi yang mudah dibaca, bukan grid
panel kecil. Tulis judul singkat, maksimal tiga pesan utama per slide kecuali
roadmap yang berisi lima tahap. Jangan mengecilkan font untuk memasukkan matriks
29 kolom atau JSON mentah; pindahkan ke backup/lampiran.

Kode MIT, dokumentasi orisinal CC BY-NC4.0, dataset panitia khusus kompetisi dan privat.
Di slide referensi, sebut dua dokumen panitia, buku Onno dengan edisi/bab yang
terverifikasi, kontrak proyek, PostgreSQL 18, OpenBao 2.5.5 dan library AEAD. Jangan
mengarang halaman buku atau menyatakan seluruh kode rujukan karya tim.

---

# 6. Bahan tanya jawab

Jawab langsung, sebut scope, lalu buka backup/evidence bila diminta. Tidak perlu
membacakan semua detail sebelum pertanyaan. Jawaban berikut adalah konteks yang
harus disesuaikan pembicara, bukan tanda semua masalah telah selesai.

## 1. Apa risiko utama yang diselesaikan?

Salinan plaintext membuka identitas/keuangan tanpa login aplikasi. Kami mengurangi
pemulihan field sensitif dari salinan protected, lalu mengukur sisa informasi dan
biaya layanan. Kami tidak mengklaim mencegah semua pencurian database. S01–S04.

## 2. Mengapa PostgreSQL, padahal studi kasus menyebut MySQL?

Soal final mengizinkan PostgreSQL dengan adaptasi dump yang dijelaskan dan
pelestarian fungsi/hubungan data. Sumber hanya INSERT tanpa DDL, sehingga tim
membentuk schema dan menjaga NULL, string identifier serta nol awal. Benchmark
membandingkan PostgreSQL plain/protected, bukan efek pindah engine. cadangan A01.

## 3. Mengapa tidak mengenkripsi semua kolom?

Kontrol dipilih menurut risiko dan kegunaan.25field AEAD,4 REF dan age_band
turunan dipakai untuk kebutuhan statistik. REF/pola NULL tetap surface inferensi
yang diukur; keputusan itu bukan pernyataan REF aman dipublikasikan per record.
Tiga nama identik belum dihapus karena kontrak mempertahankan kolom. S03/A02.

## 4. Mengapa kode_bank ikut FIN?

Nilainya pada sumber tidak konsisten sebagai kode institusi biasa dan menjadi
proxy ketika digabung atribut lain. Label acuan jenis nilainya non-pribadi,
namun hubungan dengan orang tetap berisiko. Kelas hukum, risiko dan domain
kripto adalah keputusan berbeda. Review manusia masih diperlukan. cadangan A01.

## 5. Apakah 0% berarti seluruh data tidak berguna bagi penyerang?

Tidak. 0% adalah ESCE untuk 25 kolom AEAD non-NULL pada artefak tanpa key yang
diperiksa. REF, NULL, panjang, equality dan legacy mapping masih terlihat.
Sumber 734 masih k=1 pada proyeksi tertentu. Jangan menyebut 0% semua leakage. S04.

## 6. Jika capability finansial bocor, apakah identitas tetap aman?

PII AEAD tidak terbuka melalui policy FIN pada probe. Tetapi FIN sendiri memuat
rekening, NPWP dan nama rekening, sehingga identifier tetap dapat terungkap;
DIE pada simulasi tersebut 100%. Pemisahan domain membatasi dekripsi, bukan
menjamin identitas tidak bisa direkonstruksi. cadangan A02.

## 7. Apakah yang disebut “key bocor” benar-benar KEK diekspor?

Model uji memakai capability/policy yang dapat memanggil operasi domain tertentu.
Itu tidak harus berarti byte KEK mentah diekspor. Sebut jenis capability dan ACL
probe, jangan menggambarkan semua skenario sebagai pencurian file KEK. A02/A04.

## 8. Bagaimana jika aplikasi dan akses Bao dikuasai bersamaan?

Kerahasiaan field yang dapat didekripsi proses tersebut tidak lagi dijamin.
svc-app memang memiliki kemampuan PII dan FIN; backend menegakkan role HTTP dan
field. Key-plane tidak otomatis mengetahui bahwa endpoint hanya boleh PII.
Pemisahan tugas, TTL/revokasi, audit dan pembatasan respons mengurangi risiko. A04.

## 9. Blind index apakah aman dari tebakan?

HMAC menghindari hash identifier tanpa kunci dan menjaga key di Bao. Namun
equality/frequency tetap bocor; capability search dengan kamus dapat memulihkan
nilai. Simulasi memakai kamus sintetis lengkap sebagai batas atas dan memulihkan
sekitar 12,24%sel AEAD, tanpa mendekripsi AES. Ini tradeoff exact search. A02/A04.

## 10. Mengapa AAD diperlukan?

Tag AES-GCM mengautentikasi ciphertext bersama AAD. Format v1 mengikat nama kolom,
UUID record dan protection_version. Bit tamper atau pemindahan ke record/kolom
lain gagal tertutup. Ini tidak otomatis mencegah delete atau rollback seluruh
snapshot database ke versi lama. cadangan A04.

## 11. Apakah UUID membuat dataset anonim?

Tidak. UUIDv4 mengurangi ketergantungan id berurutan dan menjadi bagian AAD,
tetapi legacy_row_id masih memetakan sumber. Atribut lain juga dapat membantu
inferensi. API B memakai business id yang dipetakan dan scope tetap diperiksa.
Jangan menyamakan pseudonimisasi dengan anonimitas. A02/A04.

## 12. Analyst count>=5 berarti sudah k-anonymous?

A5 hanya merilis lima marginal satu dimensi dengan count>=5. Kelompok kecil
tidak mengeluarkan label; total API null. Itu bukan k-anonymity kombinasi semua
REF, bukan differential privacy, dan tidak menjamin tahan differencing antarwaktu.
Raw table/view per record tetap ditolak untuk analyst_user. S05/A02.

## 13. Bukankah RLS cukup untuk mencegah pencuri credential?

RLS memakai principal yang di-set per transaksi. Pemegang credential app_user
dapat mengubah setting tersebut. Karena itu query scope dan otorisasi backend
tetap utama; RLS membantu pertahanan berlapis terhadap kesalahan, bukan batas
identitas kuat terhadap pencuri role tersebut. S03/A04.

## 14. Apakah DEK disimpan atau cache aktif di aplikasi?

DB menyimpan wrapped DEK, DEK plaintext dipakai di memori. Toolkit mempunyai
kemampuan cache default 15 detik, tetapi konfigurasi app saat ini dan benchmark v2
cache OFF. Python/OS tidak menjamin zeroization seluruh salinan atau swap.
Jika cache diaktifkan, revokasi bisa terlambat hingga sisa TTL. cadangan A04.

## 15. Mengapa performanya jauh lebih lambat?

Hasil mengandung query, crypto, RPC HMAC/unwrap dan transport/key service.
Diagnosis menunjukkan mean SQL jauh lebih kecil daripada mean client untuk
contoh lookup; selisih bukan bukti seluruhnya AES atau satu penyebab tertentu.
Tujuan kami melaporkan biaya dengan jujur. P01/P01A/P02 gagal; P03 error lulus.
Perbaikan tetap diperlukan sebelum mengusulkan SLA instansi. S06/A03.

## 16. Mengapa v2 membaik jika HTTPX lama sudah keep-alive?

Perubahan transport mengurangi overhead jalur dispatch/session dengan pool
eksplisit; HMAC batch juga ditambahkan untuk operasi yang sesuai. Kami tidak
mengklaim sebelumnya selalu handshake setiap request. Perbandingan naive/v2
adalah antarsesi dengan metadata, bukan isolasi kausal satu faktor. cadangan A03.

## 17. 38,62 ms itu respons aplikasi di VM?

Tidak. Itu median p95 per-run lookup NIK pada benchmark DB adapterv2 untuk 1M.
API comparison masih PLANNED pada snapshot. Jangan memindahkan metrik DB ke
HTTP endpoint, UI browser, hardware VM atau semua skenario. S06.

## 18. Apakah ulangan dan targetnya ditetapkan sebelum run?

Sesi DB naive/v2 masing-masing 112 run untuk dua skala, dua blok B-P-P-B dan
empat run per mode/skenario. Target commit 8c09a25 mendahului run dan tidak
dilonggarkan sesudah hasil. Rencana API yang dikurangi menjadi dua ulangan belum
memenuhi minimum awal tiga dan belum mempunyai hasil pada snapshot ini. A03.

## 19. Bukti layanan bekerja apa, selain unit test?

Lab terisolasi memakai PG 18/OpenBao TLS/API/Next/Chrome nyata,143 checks pada17 record
buatan tim, termasuk recovery. Web deployment100 checks/enam akun adalah scope
lain. Operator B juga mempunyai bukti A5 SQL dan satu reset VM65 smoke, tetapi
bukan full pentest. Angka tersebut tidak dijumlahkan menjadi satu sertifikasi.
S05/A06.

## 20. Mengapa bukan restore live saat presentasi?

Restore/migrasi/rotasi berisiko menghabiskan waktu dan mengubah sistem yang
sedang dipakai. Demo menggunakan read-only anggota pada lingkungan berizin,
sedangkan integrity/restore ditunjukkan dari hasil nyata sebelumnya dengan
label yang jujur. Bukti lab tersedia; tidak berpura-pura itu operasi live. Bab4.

## 21. Jika Bao hilang, apakah backup DB cukup?

Tidak. Perlu material key-plane yang cocok, kunci enkripsi backup dan HMAC,
custody/recovery, role dan sertifikat sesuai kebutuhan. Membuat pii-kek baru
dengan nama sama tidak membuka wrapper lama. Unseal volume existing dan restore
data tidak membuktikan DR seluruh key-plane pada mesin baru. cadangan A05.

## 22. Data terhapus apakah sudah hilang dari semua backup?

Drill membuktikan anggota buatan pada clone tidak muncul di backup baru setelah
delete. Backup lama tetap memuatnya sampai masa retensi berakhir. Deadline
retensi bukan scheduler purge atau bukti secure erase seluruh SSD/salinan.
Tidak ada klaim penghapusan fisik menyeluruh. cadangan A05.

## 23. Bagaimana rotasi dilakukan?

Rotate pii-kek lalu rewrap DEK wrapper tanpa mengenkripsi ulang field. Checkpoint
dan compare-and-swap membantu resume tanpa menimpa perubahan. Lab Alby membuktikan
100.734 wrapper PII v1 → v2 tetap terbaca; bukan rotasi 1M/semuaVM, FIN atau search
otomatis. Versi lama tetap diperlukan untuk arsip lama. cadangan A05.

## 24. Apakah log, filesystem dan seluruh Git history sudah bersih?

Ada pemeriksaan keluaran tertentu dan sanitasi evidence, tetapi audit final
menyeluruh terhadap secret/history/log/temp/screenshot belum lengkap. Enkripsi
field/dump tidak membuktikan physical file/WAL/log aman. Ini gap yang dinyatakan,
bukan PASS yang disimpulkan dari tidak ditemukannya masalah pada unit test. S08.

## 25. Mengapa masking tampilan berbeda dari contoh panitia?

Toolkit menyediakan format contoh, sedangkan runtimeB memakai variasi masking
yang menyembunyikan bagian berbeda; peran tertentu memang mendapat nilai sah
lengkap. Gap kesamaan format perlu keputusan tim dan retest bila diubah. Jangan
merekayasa screenshot agar tampak memakai fungsi yang sebenarnya tidak dipakai.
cadangan A06.

## 26. Berapa biaya, RPO/RTO dan kesiapan produksi?

Belum ada angka produksi tervalidasi. Storage1M sekitar 2,679× pada snapshot,
dan performa DB mempunyai overhead yang diukur. Instansi perlu menilai topologi,
latensi Bao, kapasitas/WAL/backup/clone, operator, custody, audit dan pengukuran
RPO/RTO. Prototipe bukan sertifikat patuh UU PDP atau produk HA siap operasi. S07–S08.

## 27. Penggunaan AI dan review manusia bagaimana?

AI membantu implementasi, test, audit dan penulisan. Evidence otomatis tidak
menggantikan reviewer kelas data/risiko, review klaim dan persetujuan final.
Jangan mengisi nama/approval yang belum diberikan. Dokumentasi dan kode tetap
mengikuti lisensi masing-masing; dataset panitia tidak dipublikasikan. S08/A06.

---

# 7. Checklist sebelum membuat dan membekukan deck

## Apa yang telah disiapkan oleh paket konteks

Lima pokok soal, alur delapan slide, waktu inti/versi panjang, narasi, spesifikasi
grafik, data CSV, diagram, ID bukti, batas klaim, rencana demo dan bahan Q&A.
Data berasal dari sumber yang diikat hash. Tidak ada benchmark baru atau login
ke deployment dalam penyusunan paket ini.

## Yang masih harus dikerjakan pembuat deck/tim

- Buat PPTX/Slides/PDF final sesuai template dan keputusan tim. Belum ada deck
  final yang dihasilkan tugas konteks ini. Nama pembicara/reviewer harus nyata.
- Cocokkan hasil API terbaru bila memang sudah menjadi evidence yang dapat
  diperiksa. Sampai saat itu tulis PLANNED/BELUM DIUJI; jangan mengambil angka DB.
- Reviewer memeriksa klasifikasi, alasan risiko, narasi FIN/search, A5, hasil gagal,
  scope pengujian dan izin materi yang akan ditampilkan.
- Pilih lingkungan demo dan operator yang berwenang. Siapkan fixture/akun/TLS,
  verifikasi commit/current state dan rekam cadangan bila diperlukan. Tidak ada
  video/screenshot/fixture runtime baru yang dibuat oleh paket konteks.
- Periksa setiap slide dan notes: tidak ada credential, token/cookie, key/share,
  source record lengkap, URL berpassword, nama folder privat atau history terminal.
- Labeli ilustrasi, data hasil, rekaman dan demo live secara berbeda. Jangan
  memotong footnote yang mengubah arti angka. Data di balik grafik juga direview.
- Latih dengan timer: versi inti300 detik; versi panjang840 detik termasuk 240 detik demo dan
  buffer60 detik. Sisihkan Q&A terpisah, bukan menambah demo di luar waktu.
- Uji keterbacaan di proyektor dan exportPDF; periksa grafik, crop, font, overlap,
  sumber dan konsistensi angka. Pemeriksaan konteks bukan pemeriksaan visual deck.
- Pastikan slide backup yang mungkin dibuka sudah berada di file yang dikumpulkan.
  Samakan hash/revisi berkas presentasi final dengan pengumpulan sesuai ketentuan.
- Tim memeriksa akses juri ke folder Drive/lampiran serta rundown terbaru.
  Paket ini tidak mengunggah, memublikasikan atau menyerahkan karya otomatis.

## Isi yang harus terlihat sebelum selesai

| Pokok | Pertanyaan pemeriksa |
|---|---|
| Risiko | Apa yang bocor, siapa penyerangnya, capability apa, dan apa yang masih terlihat? |
| Prioritas | Mengapa kontrol ini dipilih, kolom mana yang dilindungi/dipertahankan, dan tradeoff apa? |
| Bukti | Ada numerator/denominator, field/populasi, sumber dan scope tanpa mengklaim universal? |
| Kinerja | DB/API terpisah, unit/ulangan jelas, target gagal ditampilkan dan sumber sesuai sesi? |
| Penerapan | Ada urutan, operator/owner, fresh target, validasi/rollback, recovery dan pekerjaan lanjut? |

Jika salah satu jawaban belum jelas, perbaiki narasi/data sebelum dekorasi.
Tidak perlu mengisi layar dengan seluruh 15 luaran. Repo, README, matriks lengkap,
script, raw dan SBOM menjadi lampiran yang dirujuk; presentasi memaparkan keputusan
serta bukti terpilih yang menjawab kelima pokok.
