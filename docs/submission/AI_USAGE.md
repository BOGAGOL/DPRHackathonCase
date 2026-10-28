# Penggunaan AI dan review manusia

Tim menggunakan agen AI untuk membantu implementasi, test, audit perbedaan antar
modul, penyusunan dokumentasi, dan penataan bahan pengumpulan. Ini bukan bukti
bahwa seluruh rekomendasi AI benar atau telah direview manusia.

Bukti pemeriksaan otomatis disimpan di evidence/. Hasil dibedakan antara unit,
mock, lab nyata, deployment web, dan benchmark resmi. Test dapat mengurangi risiko
kesalahan implementasi tetapi tidak menggantikan keputusan klasifikasi/risiko manusia.

Sebelum finalisasi, anggota tim harus mengisi catatan review berikut pada dokumen
kerja/PR dan mengadaptasi pernyataan ini sesuai pemakaian sebenarnya:

| Area | Bukti yang direview | Reviewer manusia | Status |
|---|---|---|---|
| Klasifikasi dan ground truth | scanner/ground_truth_eval.csv + metodologi | Belum dicatat | PERLU REVIEW |
| Profile/matriks risiko | policy/protection_profile.yaml + risk-matrix.csv | Belum dicatat | PERLU REVIEW |
| Kripto/role/backup | diff A + test vectors + evidence | Belum dicatat | PERLU REVIEW |
| Backend/frontend | policy/DTO + acceptance + test B | Belum dicatat | PERLU REVIEW |
| Angka kinerja/leakage | raw, metodologi, target comparison | Belum dicatat | PERLU REVIEW |
| Laporan/slide/atribusi | setiap klaim vs indeks evidence | Belum dicatat | PERLU REVIEW |

Jangan mengisi nama/tanda tangan reviewer atau persetujuan yang belum diberikan.
Jangan menampilkan percakapan/credential/material kunci sebagai lampiran penggunaan AI.
