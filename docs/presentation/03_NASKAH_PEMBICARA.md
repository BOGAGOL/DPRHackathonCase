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
