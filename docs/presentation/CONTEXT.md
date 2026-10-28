# Konteks slide dan demo

Status: outline/naskah kerja, belum slide final. Ambil angka hanya dari
[indeks evidence](../evidence_index.md); bahan laporan di [CONTEXT](../report/CONTEXT.md).
Siapkan inti lima menit dan versi lengkap maksimum 15 menit termasuk demo, lalu
Q&A maksimum 10 menit sesuai soal final. Konfirmasi rundown terbaru ke panitia.

| Slide | Pesan utama | Bukti/visual | Inti lima menit |
|---|---|---|---|
| 1 | Bila salinan DB bocor, apa yang tetap terbaca? | Pertanyaan dan scope sintetis | 25 detik |
| 2 | Assessment sebelum memilih kontrol | Inventory + 29 kolom, E01/E02 | 40 detik |
| 3 | Pisahkan data, aplikasi dan key plane | Diagram arsitektur | 45 detik |
| 4 | AEAD/AAD, DEK per record/domain dan exact lookup HMAC | Alur kripto; tamper/swap E03 | 45 detik |
| 5 | Pengguna hanya menerima data sesuai izin | Role matrix dan A5, E09–E12 | 45 detik |
| 6 | Backup dapat dipulihkan dan rusak ditolak | E07/E10; scope 17 lab vs deployment | 40 detik |
| 7 | Kinerja dan leakage: tampilkan hasil beserta batas | E13 + after bila sudah direview | 35 detik |
| 8 | Tahapan penerapan dan risiko tersisa | Roadmap, limitations, checklist | 25 detik |

Untuk versi 15 menit, sediakan 5–6 menit demo dan ruang menjelaskan metode/hasil.
Jangan mengisi grafik after/leakage dengan angka rencana. Tampilkan "belum diuji"
atau hasil gagal secara eksplisit bila evidence belum selesai.

## Demo yang disarankan

1. Halaman login HTTPS, operator membuka daftar/detail termasking.
2. Finance melihat FIN sesuai izin; role lain tidak menerima field itu pada JSON.
3. Anggota hanya record sendiri; permintaan ID lain ditolak.
4. Analyst hanya agregat count>=5; filter cohort ditolak, raw view SQL ditolak pada
   lab yang diizinkan. Jangan mengetik credential DB di terminal presentasi.
5. Tampilkan ringkasan evidence restore/tamper dan hash artefak; jangan melakukan
   restore/migrasi berat pada database benchmark saat presentasi.

Gunakan fixture sintetis untuk screenshot/video, tanpa password, token, cookie,
material recovery atau nilai pribadi lengkap. Siapkan cadangan demo yang sesuai
evidence; rekaman bukan pengganti penjelasan bahwa operasi live belum diuji.

## Pertanyaan yang perlu siap dijawab

- Mengapa PostgreSQL diperbolehkan dan bagaimana dump diadaptasi?
- Mengapa kode_bank dienkripsi sementara REF tertentu dibiarkan?
- Apa yang bocor lewat blind index, REF dan pola NULL?
- Mengapa suppression marginal tidak sama dengan anonimisasi menyeluruh?
- Apa akibat aplikasi dan capability decrypt dikuasai bersama?
- Bagaimana mengembalikan data jika key-plane hilang, dan apa yang belum dibuktikan?
- Apa perbedaan unit/mock, lab 17 record, deployment web dan benchmark resmi?
- Berapa overhead dan hasil target P01–P03? Jawab hanya bila hasil resmi tersedia.

Final: samakan file yang dikumpulkan dan dipresentasikan, verifikasi akses folder,
nama tim/atribusi, sumber caption, status hasil serta batas waktu. Tidak ada
persetujuan reviewer, hasil benchmark atau slide final yang dibuat-buat oleh outline ini.
