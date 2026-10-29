# 8. Keterbatasan, kesimpulan yang sah dan pekerjaan manusia

## Batas desain dan pembuktian

| Area | Yang boleh disimpulkan | Yang belum atau tidak boleh disimpulkan |
|---|---|---|
| Field AEAD | Format v1, anti-tamper/swap dan fail closed dalam test | Seluruh disk, WAL, temp, log dan setiap snapshot historis aman |
| Dump tanpa key | ESCE 0 untuk 25 field AEAD pada artefak yang diuji | Nol informasi pribadi atau inferensi dari semua atribut |
| Pemisahan FIN/PII | Domain AEAD lain ditolak dalam probe | FIN bocor tidak mengungkap identitas; svc-app tidak dapat membuka FIN |
| Search HMAC | Key tidak diekspor dan exact lookup tersedia | Aman dari dictionary jika capability dan kamus ikut bocor |
| REF/metadata | Ditahan untuk fungsi, residual diukur | Semua metadata non-pribadi atau UUID menganonimkan record |
| k-anonymity | Minimum k pada atribut, proyeksi dan populasi tertentu | k seluruh kombinasi, sumber 734 anonim, atau differential privacy |
| A5 | SQL aggregate-only, marginal >=5, tidak merilis label kelompok 1–4 | Dump tidak mengandung REF atau tahan differencing antarwaktu |
| RLS | Lapisan tambahan scope query | Tahan pemegang credential app_user yang dapat mengganti principal |
| svc-app | Token TTL/policy dan otorisasi field di backend | Bao otomatis membatasi FIN hanya untuk endpoint finance |
| Cache/memori | TTL/ukuran terbatas, app cache OFF, cleanup best effort | Zeroization seluruh salinan Python/OS/swap/crash dump |
| TLS | CA/hostname diperiksa dan negative test lab | Seluruh cloud routing, security group dan certificate renewal telah diaudit |
| Masking | Toolkit mengikuti contoh panitia, runtime B memakai variasi | Semua tampilan aplikasi persis mengikuti format toolkit/panitia |
| Backup | GCM/HMAC/digest, tanpa file dump plaintext, restore baru | Seluruh DR VM, kehilangan Bao dan escrow kunci telah teruji |
| Retensi | Record tidak masuk backup baru setelah delete pada fixture | Backup lama hilang, secure erase SSD, atau purge terjadwal otomatis |
| Audit | Metadata minimal, query terkontrol, error generik | Audit immutable dan bebas PII pada seluruh host/history/Git |
| Scanner | Recall gabungan lebih baik pada 29 label | Generalisasi semua database atau reviewer hukum telah menyetujui |
| Kinerja DB | 112 run per sesi, target yang gagal tetap dilaporkan | Optimasi 51% berarti P01/P02 lulus, atau angka DB adalah angka API |
| Kinerja API | Runner/rencana dan histori setup tersedia | Hasil API before/after atau tujuh workload API semuanya terukur |
| Unit/acceptance | Kasus yang benar-benar dijalankan pada lingkungan tertentu | Jumlah test besar berarti keamanan universal atau seluruh populasi teruji |
| Supply chain | Requirements/lockfile/image dicatat | OS, Python transitif, versi deployment dan seluruh CVE bersih |
| VM reset | Satu guarded golden reset dan 65 smoke checks | Pentest whitebox penuh atau DR key-plane telah selesai |
| Legal/produksi | Assessment mengacu istilah UU PDP | Sertifikat patuh UU PDP, dasar hukum produksi, atau sistem resmi DPR RI |

## Kalimat yang dapat dipakai pada simpulan

“Prototipe menunjukkan bahwa pemisahan capability kunci dan enkripsi field
terautentikasi dapat mengurangi pemulihan nilai sensitif dari salinan data tanpa
kunci, dengan fungsi dan pemulihan layanan yang dibuktikan pada scope pengujian.
Sisa kebocoran metadata dan inferensi masih terlihat. Performa protected membaik
pada varian transport baru tetapi belum mencapai ambang yang ditetapkan; hasil
API belum tersedia pada snapshot. Penerapan instansi memerlukan review dan
pengujian lanjutan sesuai topologi serta proses operasionalnya.”

Hindari “100% aman”, “mustahil bocor”, “nol leakage semua data”, “sepenuhnya patuh
UU PDP”, “semua bencana dapat dipulihkan”, “pentest selesai”, atau “seluruh target
terpenuhi”. Keberhasilan operasional runner bukan kelulusan target kinerja.

## Gap bukti yang harus tampak di laporan

- S05: scan seluruh secret aktif pada Git history/repo/dump/backup/log belum
  disatukan sebagai evidence final menyeluruh. Scan lokal terbatas tidak boleh
  dinamai audit seluruh riwayat.
- S06: general/slow/error/app log, temp, history, ekspor dan dokumentasi/screenshot
  perlu daftar cakupan masing-masing. Pengecualian dataset panitia berlaku pada
  path persis yang diizinkan, bukan semua SQL atau seluruh folder evidence.
- Pencurian file data fisik/WAL tidak dibuktikan hanya oleh COPY/dump ciphertext.
- Custody lintas operator, restore key-plane pada mesin baru, certificate renewal,
  purge arsip/secure erase dan RPO/RTO belum dibuktikan menyeluruh.
- API masih PLANNED; rencana dua ulangan tidak memenuhi minimum tiga. Operasi
  update/insert/mixed API belum terukur. Hasil baru harus punya file/commit/scope
  sendiri sebelum mengganti status ini.
- Matriks semua role DB pada setiap deployment dan kompatibilitas live app setelah
  transport baru tetap dipisahkan dari unit, lab dan probe historis.
- Format masking runtime membutuhkan keputusan tim: selaraskan format atau
  jelaskan variasi dan justifikasinya. Tugas konteks ini tidak mengubah aplikasi.

## Review manusia yang harus dicatat

| Objek | Keputusan yang perlu diperiksa | Status dalam paket konteks |
|---|---|---|
| Ground truth 29 kolom | nip_kppn, institusi, kelas, jenis dan risiko | Pengesahan final belum dicatat |
| Profile/risiko | Alasan REF, kode_bank FIN, minimisasi dan residual | Review tim diperlukan |
| Kripto/Transit/pool | TLS/error/batch/close, format v1 dan konsumen | Unit/evidence ada; bukan approval seseorang |
| Role/DTO/masking | Hak aktual dan kesesuaian contoh panitia | Gap masking dijelaskan |
| DB/API/leakage | Commit, scope, median, pengganti AC dan target gagal | DB ada, API pending |
| Laporan/slide | Klaim, angka, gambar, atribusi, lisensi dan privasi | Belum PDF/slide final |

Jangan mengisi nama, tanda tangan atau approval yang belum diberikan. AI membantu
implementasi, test, audit dan penulisan; tanggung jawab review tetap manusia.
Dokumentasi orisinal CC BY-NC 4.0, kode MIT, data panitia tetap privat khusus
kompetisi, dan dependensi mengikuti lisensi asal.
