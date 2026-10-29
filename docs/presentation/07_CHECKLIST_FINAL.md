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
