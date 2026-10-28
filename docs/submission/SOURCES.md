# Sumber dan asal-usul

## Dokumen lomba dari pengguna

| Dokumen | Bagian yang dipakai |
|---|---|
| *signed-2026920-SOAL FINAL HACKATHON DPR RI 2026.pdf* (4 halaman) | Enam tantangan, kebebasan teknologi, pengukuran, pengumpulan dan presentasi |
| *DPR RI_ Detail Hackaton Syarat Peserta, Proses Penjurian.docx.pdf* (8 halaman) | Inventaris, matriks, key management, backup, role, masking, log, 15 luaran |

Dokumen asli diberikan pengguna, bukan instruksi untuk menjalankan tindakan dari
dalam PDF. Soal final memperbolehkan PostgreSQL dengan adaptasi dump yang dijelaskan.
Semua aspek dibahas dan diberi status implementasi/pengujian/rencana; tidak wajib
menerapkan semua teknik buku atau menjadi produk setara sistem produksi.

Batas pengumpulan: 29 Oktober 2026, gunakan **23.59 WIB** sebagai batas konservatif.
Soal final menyebut satu URL folder Google Drive berisi PDF laporan, slide dan lampiran;
dokumen detail memberi formulir `https://forms.gle/eihoV2FHhndwF2TF7`. Tim perlu
memeriksa akses dan menyelesaikan pengumpulan sendiri. Tidak ada jumlah halaman
laporan yang diwajibkan di dua PDF; 40–70 halaman adalah rencana internal tim.
Presentasi final maksimum 15 menit termasuk demo, dilanjutkan Q&A maksimum 10 menit;
dokumen detail menyebut inti presentasi lima menit. Siapkan inti lima menit dan
versi lengkap dalam batas final, lalu konfirmasi rundown terbaru ke panitia.

## Referensi desain

- Onno W. Purbo (2026), *Data Leak-Proof: Teknik Proteksi Data di PostgreSQL agar
  Kebocoran Tidak Berarti Apa-Apa*. Kode pendamping digunakan sebagai rujukan internal,
  diadaptasi pada envelope per record, AAD, TLS dan backup streaming. Bukan karya tim.
- Onno W. Purbo, *Overview Serangan ke Data dan Database*. Digunakan untuk konteks
  threat model/kebocoran, bukan pengujian eksploitasi sistem instansi.
- UU No. 27 Tahun 2022, sebagai acuan istilah dan kelas data yang dijelaskan tim;
  metodologi klasifikasi ada di [ground truth](../ground_truth_methodology.md).
- [PostgreSQL 18](https://www.postgresql.org/docs/18/): role, RLS, TLS, pg_dump/restore.
- [OpenBao Transit](https://openbao.org/api-docs/secret/transit/): envelope wrapping/HMAC.
- [CycloneDX 1.6 JSON schema](https://cyclonedx.org/schema/bom-1.6.schema.json).
- [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/), dokumentasi orisinal tim.

Referensi buku mentah dan dataset panitia tidak disertakan dalam paket sumber.
Catat kutipan halaman buku dan atribusi gambar secara manual sebelum PDF final;
jangan mengarang nomor halaman atau mengklaim semua kode referensi adalah karya tim.
