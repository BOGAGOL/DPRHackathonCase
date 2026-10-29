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
