# Prompt serah-terima kepada penulis/AI lain

Anda membantu Tim BOGAGOL menyusun laporan/panduan teknis PDF Final Hackathon DPR RI
2026. Gunakan CONTEXT.md dalam folder ini sebagai konteks utama, serta tabel CSV,
evidence_snapshot.json dan diagram pada assets/ sebagai lampiran terstruktur.

Keluaran yang diminta: laporan berbahasa Indonesia dengan **analisis, rancangan,
prioritas, langkah implementasi, hasil pengujian, keterbatasan, dan referensi**.
Susun enam tantangan soal sebagai alur yang mudah diperiksa juri. Semua 15 luaran
harus dipetakan, tetapi kode/raw/slide tetap merupakan berkas pendamping; jangan
memenuhi laporan dengan salinan seluruh source code atau jutaan baris raw.

Aturan faktual:

- Pisahkan “Diimplementasikan + Diuji”, “Diimplementasikan”, “Rencana”, dan
  “Belum diverifikasi”. Beri ID bukti, lingkungan, tanggal dan cakupan setiap klaim.
- Jangan menulis hasil rencana menjadi keberhasilan. Jangan membuat angka API,
  hasil pentest penuh, secure erase, full disk/WAL encryption, DR key-plane,
  persetujuan reviewer, atau kepatuhan hukum yang tidak tersedia.
- Hasil DB naive/v2 sudah ada, keduanya gagal target latensi/throughput. Nyatakan
  kegagalan tersebut meski v2 membaik. P03 error rate lulus. Angka DB bukan angka API.
- API masih PLANNED pada snapshot ini. Rencana satu blok/two repetitions tidak
  memenuhi minimum awal tiga ulangan; tuliskan sebagai deviasi metodologi.
- ESCE 0% berarti tidak ada sel AEAD non-NULL yang pulih persis pada skenario dan
  artefak yang diperiksa. Bukan 0% seluruh data/inferensi/semua bentuk kebocoran.
- FIN yang bocor membuka rekening/NPWP dan nama rekening. Jangan menulis “identitas
  tetap seluruhnya aman ketika kunci finance bocor”. Blast radius kripto dan
  kerahasiaan identitas lintas atribut adalah dua hal berbeda.
- Residual k populasi penuh yang besar tidak menghilangkan k=1 pada 734 sumber.
  Suppression A5 lima marginal bukan anonimisasi dump, differential privacy,
  atau k-anonymity semua kombinasi.
- Toolkit masking dan masking runtime B berbeda. Bahan ini mendokumentasikan
  implementasi aktual dan gap, bukan mengesahkan semua contoh panitia terpenuhi.
- Tidak ada nilai anggota lengkap, password, token, unseal share, kunci nyata,
  cookie, URL bercredential atau dump pada teks/ilustrasi/lampiran. Contoh masking
  panitia dan placeholder sintetik boleh dipakai dengan label.
- UU PDP dipakai sebagai landasan istilah/assessment, bukan sertifikat kepatuhan.
  Jangan menambah kategori spesifik pada agama, jumlah_anak atau pekerjaan Dokter
  tanpa dasar. Bedakan kelas hukum, skor risiko, dan domain kripto.
- Kutip kode/evidence sebagai sumber implementasi. Sumber primer menjelaskan
  mekanisme, tidak membuktikan bahwa konfigurasi proyek telah berjalan.
- Nomor halaman buku yang belum diperiksa tidak boleh dikarang. Angka yang
  dibulatkan harus konsisten dengan tabel penuh, unit dan denominator.

Mulai dengan outline dan matriks klaim–bukti. Tulis narasi per bab dengan alasan
keputusan, tradeoff dan interpretasi hasil. Tandai pekerjaan manusia sebagai
BELUM DIREVIEW, bukan mengisi nama atau tanda tangan sendiri. Bahan 40–70 halaman
adalah target internal, bukan jumlah halaman wajib pada dua PDF panitia.
