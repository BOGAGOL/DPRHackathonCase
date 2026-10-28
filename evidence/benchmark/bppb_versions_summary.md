# B-P-P-B DB: naive_v1 dan v2

Median antar empat run per mode/skenario. V2: https_pool, DEK cache OFF; target tidak berubah.
Plain disajikan terpisah untuk setiap sesi. Rasio/delta dan target memakai plain dalam sesi yang sama;
perubahan antarsesi menggambarkan hasil dua sesi terpisah, bukan pasangan run simultan.

| Skala | Skenario | Sesi | Mode | p50 ms | p95 ms | req/s | error % | db_time ms/req | Delta p95 ms | Rasio p95 | P01 | P01A | P02 | P03 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|
| 100k | read_by_nik | naive_v1 | plain | 3.507 | 6.604 | 2086.22 | 0.000000 | 0.0391 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | read_by_nik | naive_v1 | protected | 49.652 | 78.181 | 153.04 | 0.000000 | 0.1520 | 71.577 | 11.839 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | read_by_email | naive_v1 | plain | 3.480 | 6.645 | 2093.15 | 0.000000 | 0.0402 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | read_by_email | naive_v1 | protected | 48.518 | 74.941 | 157.67 | 0.000000 | 0.1448 | 68.297 | 11.279 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | read_profile | naive_v1 | plain | 3.663 | 7.281 | 1965.33 | 0.000000 | 0.0326 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | read_profile | naive_v1 | protected | 36.085 | 58.196 | 209.50 | 0.000000 | 0.1363 | 50.915 | 7.992 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | list_page | naive_v1 | plain | 2.758 | 5.386 | 2550.93 | 0.000000 | 0.0943 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | list_page | naive_v1 | protected | 37.784 | 59.953 | 201.75 | 0.000000 | 3.5644 | 54.566 | 11.131 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | update_contact | naive_v1 | plain | 5.998 | 10.587 | 1193.17 | 0.000000 | 0.2568 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | update_contact | naive_v1 | protected | 30.405 | 47.164 | 248.61 | 0.000000 | 1.6418 | 36.577 | 4.455 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | insert_member | naive_v1 | plain | 9.406 | 15.629 | 772.80 | 0.000000 | 0.1760 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | insert_member | naive_v1 | protected | 120.794 | 171.968 | 63.71 | 0.000000 | 1.6692 | 156.339 | 11.003 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | mixed | naive_v1 | plain | 4.815 | 17.043 | 1166.89 | 0.000000 | 0.1134 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | mixed | naive_v1 | protected | 44.224 | 130.875 | 144.38 | 0.000000 | 0.8665 | 113.832 | 7.679 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | read_by_nik | v2 | plain | 2.966 | 5.494 | 2492.10 | 0.000000 | 0.0334 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | read_by_nik | v2 | protected | 25.673 | 37.734 | 300.45 | 0.000000 | 0.1420 | 32.239 | 6.868 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | read_by_email | v2 | plain | 2.954 | 5.482 | 2497.87 | 0.000000 | 0.0336 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | read_by_email | v2 | protected | 25.331 | 37.225 | 303.97 | 0.000000 | 0.1402 | 31.743 | 6.790 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | read_profile | v2 | plain | 2.962 | 5.464 | 2499.99 | 0.000000 | 0.0269 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | read_profile | v2 | protected | 20.204 | 30.474 | 380.42 | 0.000000 | 0.1308 | 25.010 | 5.577 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | list_page | v2 | plain | 2.371 | 4.163 | 3092.95 | 0.000000 | 0.0826 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | list_page | v2 | protected | 27.730 | 42.640 | 276.03 | 0.000000 | 3.6032 | 38.477 | 10.243 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | update_contact | v2 | plain | 5.151 | 7.803 | 1457.88 | 0.000000 | 0.2176 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | update_contact | v2 | protected | 18.984 | 28.441 | 397.96 | 0.000000 | 1.7360 | 20.638 | 3.645 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | insert_member | v2 | plain | 8.244 | 12.537 | 917.42 | 0.000000 | 0.1443 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | insert_member | v2 | protected | 55.036 | 79.607 | 139.02 | 0.000000 | 1.8801 | 67.070 | 6.350 | GAGAL | GAGAL | GAGAL | LULUS |
| 100k | mixed | v2 | plain | 3.451 | 10.041 | 1733.42 | 0.000000 | 0.0791 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 100k | mixed | v2 | protected | 25.953 | 61.960 | 262.74 | 0.000000 | 0.9880 | 51.920 | 6.171 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | read_by_nik | naive_v1 | plain | 3.080 | 5.747 | 2391.58 | 0.000000 | 0.0348 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | read_by_nik | naive_v1 | protected | 48.643 | 78.967 | 155.34 | 0.000000 | 0.1563 | 73.219 | 13.740 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | read_by_email | naive_v1 | plain | 3.058 | 5.747 | 2404.55 | 0.000000 | 0.0343 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | read_by_email | naive_v1 | protected | 46.309 | 72.900 | 163.52 | 0.000000 | 0.1484 | 67.153 | 12.686 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | read_profile | naive_v1 | plain | 3.104 | 5.848 | 2372.00 | 0.000000 | 0.0282 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | read_profile | naive_v1 | protected | 33.811 | 54.888 | 225.29 | 0.000000 | 0.1318 | 49.040 | 9.385 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | list_page | naive_v1 | plain | 2.480 | 4.551 | 2919.07 | 0.000000 | 0.0847 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | list_page | naive_v1 | protected | 35.780 | 56.524 | 213.29 | 0.000000 | 3.3867 | 51.973 | 12.421 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | update_contact | naive_v1 | plain | 5.371 | 8.127 | 1396.68 | 0.000000 | 0.2286 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | update_contact | naive_v1 | protected | 27.136 | 39.482 | 283.86 | 0.000000 | 1.4126 | 31.354 | 4.858 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | insert_member | naive_v1 | plain | 8.390 | 12.684 | 910.57 | 0.000000 | 0.1529 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | insert_member | naive_v1 | protected | 124.141 | 189.152 | 61.85 | 0.000000 | 1.6674 | 176.468 | 14.912 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | mixed | naive_v1 | plain | 3.633 | 10.651 | 1631.83 | 0.000000 | 0.1079 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | mixed | naive_v1 | protected | 41.895 | 124.898 | 152.67 | 0.000000 | 0.8360 | 114.247 | 11.727 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | read_by_nik | v2 | plain | 3.296 | 6.064 | 2260.06 | 0.000000 | 0.0398 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | read_by_nik | v2 | protected | 26.257 | 38.624 | 293.61 | 0.000000 | 0.1802 | 32.560 | 6.370 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | read_by_email | v2 | plain | 3.305 | 6.069 | 2260.65 | 0.000000 | 0.0401 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | read_by_email | v2 | protected | 27.874 | 42.832 | 274.78 | 0.000000 | 0.1891 | 36.763 | 7.057 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | read_profile | v2 | plain | 3.020 | 5.602 | 2445.83 | 0.000000 | 0.0297 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | read_profile | v2 | protected | 21.455 | 33.722 | 357.20 | 0.000000 | 0.1472 | 28.120 | 6.020 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | list_page | v2 | plain | 2.443 | 4.321 | 3006.53 | 0.000000 | 0.0886 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | list_page | v2 | protected | 29.443 | 45.564 | 260.53 | 0.000000 | 4.2628 | 41.242 | 10.544 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | update_contact | v2 | plain | 5.222 | 8.027 | 1433.21 | 0.000000 | 0.2356 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | update_contact | v2 | protected | 19.877 | 31.649 | 374.46 | 0.000000 | 1.9662 | 23.622 | 3.943 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | insert_member | v2 | plain | 8.457 | 12.767 | 902.15 | 0.000000 | 0.1614 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | insert_member | v2 | protected | 59.643 | 82.176 | 130.43 | 0.000000 | 2.1132 | 69.408 | 6.436 | GAGAL | GAGAL | GAGAL | LULUS |
| 1m | mixed | v2 | plain | 3.567 | 10.380 | 1667.08 | 0.000000 | 0.0993 | 0.000 | 1.000 | ACUAN | ACUAN | ACUAN | ACUAN |
| 1m | mixed | v2 | protected | 28.449 | 67.520 | 240.88 | 0.000000 | 1.2013 | 57.139 | 6.505 | GAGAL | GAGAL | GAGAL | LULUS |

V2 status: COMPLETED; integritas akhir: True; error terukur: 0; blok invalid/disimpan: 0.
Semua raw gzip dan metadata berada di direktori masing-masing versi. Tidak menghapus run buruk.
db_time adalah mean SQL execution/request, bukan percentile server; non-DB tetap tersedia dalam JSON.

## Level API — gate awal 29 Oktober 2026, 05:05 WIB

**BELUM DIUJI**, skala100k: api_list_page, api_read_profile, api_search_nik dan api_search_email. Token svc-app terbaru ditolak lookup-self HTTP403; syarat policy hanya svc-app dan sisa TTL >=2 jam belum terverifikasi. Seluruh metrik latency/throughput/error dan P01/P01A/P02/P03 API belum dinilai. Tidak ada parity atau workload dijalankan, salinan api_* belum dibuat.

Rancangan API memakai TLS DB pada kedua mode, HTTPS+FastAPI+audit log dan DTO endpoint; kondisi ini berbeda dari DB v2 (baseline DB tanpa TLS), sehingga tidak boleh mencampur percentile/rasio lintas level. Hasil DB di atas tetap dipertahankan. Bukti gate: evidence/benchmark/api_bppb_100k/preflight_20261029T050503WIB.json; snapshot kode51c8ca3. Lanjut hanya setelah operator menyediakan token yang memenuhi syarat dan semua gate awal diulang.
