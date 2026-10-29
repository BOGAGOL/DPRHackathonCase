# Hasil reproduksi pengumpulan — clone bersih

`setup` dijalankan pada clone baru tanpa virtualenv/node_modules/.next atau config
lokal developer. Input 734 record panitia berasal dari source privat yang diizinkan;
tidak menjadi fixture unit baru atau disalin ke report. Semua service baru pada port
acak; pg-dpr/deployment tim tidak dihubungi. Bukan benchmark resmi.

| Run | Status | Cakupan |
|---|---|---|
| [20261029T094522Z-44664b0c](20261029T094522Z-44664b0c/summary.json) | PASS | Jalur native PG18/OpenBao2.5.5 TLS, semua 734 field-row dibandingkan, resume, 6 akun, 100 check Chrome, backup/restore/tamper/retention |
| [20261029T094825Z-ecd290d1](20261029T094825Z-ecd290d1/summary.json) | PASS | Pengulangan lengkap melalui `demo --demo-seconds 3`, termasuk startup frontend/API interaktif dan shutdown |
| [20261029T093915Z-8b8a060c](20261029T093915Z-8b8a060c/summary.json) | FAIL | Docker engine belum operasional; diagnosis operator berikutnya: API engine 500 |
| [20261029T093930Z-66a3dc9d](20261029T093930Z-66a3dc9d/summary.json) | FAIL | Percobaan awal native terhenti karena handle pipe Windows; cluster invocation kemudian dihentikan tepat identitas run tersebut |
| [20261029T094116Z-7b38e0ef](20261029T094116Z-7b38e0ef/summary.json) | FAIL | Scanner selesai, profile builder belum mengenali vocabulary rekomendasi scanner terbaru; sudah diperbaiki |
| [20261029T094336Z-b6f49a01](20261029T094336Z-b6f49a01/summary.json) | FAIL | Layanan/restore/Chrome lulus tetapi loader vector Unicode launcher memakai encoding ANSI Windows; sudah diperbaiki menjadi UTF-8 |

Report setiap run tetap hasil asli. Riwayat gagal tidak dibuang atau diganti PASS.
Pada versi awal, gagal startup stack tercatat `preflight`; versi berikutnya
memisahkannya sebagai `setup`. Native dan Docker memakai transport PG tools berbeda;
PASS native tidak dianggap PASS Docker. CLI/setup baru berada di `infra/reproduce/`.

`browser.json` hanya boolean/scope, bukan response data. Scanner menulis contoh
termasking dan statistik, bukan dump. Password/token/shares/key/PG data/log privat
berada di temporary private directory luar repo, tidak disalin ke sini.

[Receipt akhir](final-verification.json) memetakan commit, hash report, versi dan
hasil regresi. Laporan historis di kategori lain tidak ditimpa oleh run ini.
