# 11. Tabel siap olah untuk laporan

Angka penuh ada di CSV/JSON; Markdown membulatkan6desimal. PASS/FAIL menunjukkan hasil target atau boolean sesuai kolom, bukan kelengkapan lomba.


## Matriks29kolom

Kelas acuan, risiko acuan dan risiko scanner dapat berbeda; domain bukan kelas hukum. Proyeksi analis adalah bahan agregat A5, bukan hak per-record.

| Kolom | Kelas acuan | Risiko acuan | Risiko scanner | Domain | Storage | Bidx | Normalisasi |
|---|---|---|---|---|---|---|---|
| nama | umum | sedang | tinggi | PII | nama_ct | — | — |
| nama_lengkap | umum | sedang | tinggi | PII | nama_lengkap_ct | — | — |
| nama_tanpa_gelar | umum | sedang | tinggi | PII | nama_tanpa_gelar_ct | — | — |
| jenis_kelamin | umum | rendah | kritis | REF | jenis_kelamin | — | — |
| tempat_lahir | umum | sedang | kritis | PII | tempat_lahir_ct | — | — |
| tanggal_lahir | umum | tinggi | kritis | PII | tanggal_lahir_ct | — | — |
| tanggal_pernikahan | umum | sedang | kritis | PII | tanggal_pernikahan_ct | — | — |
| no_ktp | umum | kritis | kritis | PII | no_ktp_ct | no_ktp_bidx | ascii_digits_preserve_leading_zero |
| pekerjaan_terakhir | umum | rendah | tinggi | REF | pekerjaan_terakhir | — | — |
| alamat_jakarta | umum | tinggi | kritis | PII | alamat_jakarta_ct | — | — |
| alamat_daerah | umum | tinggi | kritis | PII | alamat_daerah_ct | — | — |
| telpon_jakarta | umum | tinggi | kritis | PII | telpon_jakarta_ct | — | — |
| telpon_daerah | umum | tinggi | kritis | PII | telpon_daerah_ct | — | — |
| handphone | umum | tinggi | kritis | PII | handphone_ct | — | — |
| email | umum | tinggi | kritis | PII | email_ct | email_bidx | strip_lower |
| ruangan | umum | sedang | tinggi | PII | ruangan_ct | — | — |
| status_kawin | umum | sedang | kritis | PII | status_kawin_ct | — | — |
| jumlah_anak | umum | sedang | tinggi | PII | jumlah_anak_ct | — | — |
| jumlah_tanggungan | umum | sedang | tinggi | PII | jumlah_tanggungan_ct | — | — |
| jumlah_jiwa | umum | sedang | tinggi | PII | jumlah_jiwa_ct | — | — |
| rekening | spesifik | kritis | kritis | FIN | rekening_ct | — | — |
| nama_rekening | umum | tinggi | tinggi | FIN | nama_rekening_ct | — | — |
| npwp | umum | tinggi | kritis | FIN | npwp_ct | — | — |
| kode_bank | non-pribadi | rendah | tinggi | FIN | kode_bank_ct | — | — |
| nama_kppn | non-pribadi | rendah | kritis | REF | nama_kppn | — | — |
| nama_bank | non-pribadi | rendah | kritis | REF | nama_bank | — | — |
| nip_kppn | umum | tinggi | kritis | PII | nip_kppn_ct | — | — |
| pengguna | umum | tinggi | tinggi | PII | pengguna_ct | pengguna_bidx | strip_case_sensitive |
| agama | umum | tinggi | kritis | PII | agama_ct | — | — |

## Validasi migrasi

| Target | Source | Baris | Validasi | Hasil |
|---|---|---|---|---|
| protected_734 | postgres | 734 | all_rows_all_fields | PASS |
| protected_100k | baseline_100k | 100000 | all_rows_all_fields | PASS |
| protected_1m | baseline_1m | 1000000 | all_rows_all_fields | PASS |

## ESCE dan DIE —25field AEAD non-NULL

| Dataset | Skenario | ESCE n | ESCE d | ESCE % | DIE % |
|---|---|---|---|---|---|
| baseline_100k | baseline_dump | 2449994 | 2449994 | 100.000000 | 100.000000 |
| protected_100k | protected_dump_no_key | 0 | 2449994 | 0.000000 | 0.000000 |
| protected_100k | protected_dump_with_pii_key | 2049994 | 2449994 | 83.673429 | 100.000000 |
| protected_100k | protected_dump_with_finance_key | 400000 | 2449994 | 16.326571 | 100.000000 |
| protected_100k | protected_dump_with_search_key | 300000 | 2449994 | 12.244928 | 100.000000 |
| baseline_1m | baseline_dump | 24500005 | 24500005 | 100.000000 | 100.000000 |
| protected_1m | protected_dump_no_key | 0 | 24500005 | 0.000000 | 0.000000 |
| protected_1m | protected_dump_with_pii_key | 20500005 | 24500005 | 83.673473 | 100.000000 |
| protected_1m | protected_dump_with_finance_key | 4000000 | 24500005 | 16.326527 | 100.000000 |
| protected_1m | protected_dump_with_search_key | 3000000 | 24500005 | 12.244895 | 100.000000 |

## Residual1–3atribut

| Dataset | Populasi | Proyeksi | Minimum k | Maks baris singleton satu proyeksi |
|---|---|---|---|---|
| protected_100k | all | 41 | 136 | 0 |
| protected_100k | source_734 | 41 | 1 | 11 |
| protected_100k | synthetic | 41 | 135 | 0 |
| protected_1m | all | 41 | 1362 | 0 |
| protected_1m | source_734 | 41 | 1 | 11 |
| protected_1m | synthetic | 41 | 1361 | 0 |

## DB naive_v1 —median4run/mode/skenario

| Skala | Skenario | B p50 ms | P p50 ms | B p95 ms | P p95 ms | B req/s | P req/s | P01 | P01A | P02 | P03 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 100k | read_by_nik | 3.507300 | 49.652275 | 6.603700 | 78.181190 | 2086.219454 | 153.038440 | FAIL | FAIL | FAIL | PASS |
| 100k | read_by_email | 3.479975 | 48.518475 | 6.644570 | 74.941457 | 2093.145387 | 157.668298 | FAIL | FAIL | FAIL | PASS |
| 100k | read_profile | 3.663150 | 36.085150 | 7.281435 | 58.195950 | 1965.329323 | 209.497220 | FAIL | FAIL | FAIL | PASS |
| 100k | list_page | 2.758150 | 37.783625 | 5.386192 | 59.952507 | 2550.926479 | 201.745924 | FAIL | FAIL | FAIL | PASS |
| 100k | update_contact | 5.997550 | 30.404700 | 10.587218 | 47.164460 | 1193.167874 | 248.610709 | FAIL | FAIL | FAIL | PASS |
| 100k | insert_member | 9.405925 | 120.793975 | 15.629310 | 171.968142 | 772.803866 | 63.708950 | FAIL | FAIL | FAIL | PASS |
| 100k | mixed | 4.815025 | 44.223875 | 17.042535 | 130.874502 | 1166.890628 | 144.380317 | FAIL | FAIL | FAIL | PASS |
| 1m | read_by_nik | 3.080450 | 48.642650 | 5.747112 | 78.966515 | 2391.578009 | 155.336478 | FAIL | FAIL | FAIL | PASS |
| 1m | read_by_email | 3.057900 | 46.308650 | 5.746653 | 72.899642 | 2404.549218 | 163.517728 | FAIL | FAIL | FAIL | PASS |
| 1m | read_profile | 3.103650 | 33.811250 | 5.848390 | 54.888380 | 2372.001823 | 225.292774 | FAIL | FAIL | FAIL | PASS |
| 1m | list_page | 2.480150 | 35.779975 | 4.550530 | 56.523755 | 2919.068391 | 213.286402 | FAIL | FAIL | FAIL | PASS |
| 1m | update_contact | 5.371300 | 27.136050 | 8.127015 | 39.481502 | 1396.684267 | 283.858876 | FAIL | FAIL | FAIL | PASS |
| 1m | insert_member | 8.390000 | 124.141200 | 12.684437 | 189.152275 | 910.569744 | 61.846172 | FAIL | FAIL | FAIL | PASS |
| 1m | mixed | 3.632875 | 41.895250 | 10.650672 | 124.898050 | 1631.827676 | 152.671425 | FAIL | FAIL | FAIL | PASS |

## DB v2 —median4run/mode/skenario

| Skala | Skenario | B p50 ms | P p50 ms | B p95 ms | P p95 ms | B req/s | P req/s | P01 | P01A | P02 | P03 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 100k | read_by_nik | 2.965925 | 25.673425 | 5.494493 | 37.733697 | 2492.097302 | 300.454386 | FAIL | FAIL | FAIL | PASS |
| 100k | read_by_email | 2.953900 | 25.330850 | 5.481930 | 37.224930 | 2497.873020 | 303.968832 | FAIL | FAIL | FAIL | PASS |
| 100k | read_profile | 2.962400 | 20.204450 | 5.464300 | 30.473875 | 2499.994569 | 380.423749 | FAIL | FAIL | FAIL | PASS |
| 100k | list_page | 2.371050 | 27.729950 | 4.162912 | 42.640405 | 3092.945217 | 276.031944 | FAIL | FAIL | FAIL | PASS |
| 100k | update_contact | 5.150900 | 18.984300 | 7.802725 | 28.440860 | 1457.876255 | 397.962873 | FAIL | FAIL | FAIL | PASS |
| 100k | insert_member | 8.243600 | 55.035800 | 12.537313 | 79.607015 | 917.416507 | 139.015457 | FAIL | FAIL | FAIL | PASS |
| 100k | mixed | 3.451075 | 25.953100 | 10.040693 | 61.960250 | 1733.418712 | 262.742462 | FAIL | FAIL | FAIL | PASS |
| 1m | read_by_nik | 3.296150 | 26.257100 | 6.063700 | 38.623677 | 2260.056826 | 293.611651 | FAIL | FAIL | FAIL | PASS |
| 1m | read_by_email | 3.304875 | 27.874250 | 6.069317 | 42.832465 | 2260.645395 | 274.777339 | FAIL | FAIL | FAIL | PASS |
| 1m | read_profile | 3.020300 | 21.455450 | 5.601655 | 33.721755 | 2445.834179 | 357.199715 | FAIL | FAIL | FAIL | PASS |
| 1m | list_page | 2.443225 | 29.442800 | 4.321497 | 45.563978 | 3006.525791 | 260.532129 | FAIL | FAIL | FAIL | PASS |
| 1m | update_contact | 5.222050 | 19.876700 | 8.027143 | 31.649040 | 1433.211814 | 374.462724 | FAIL | FAIL | FAIL | PASS |
| 1m | insert_member | 8.456700 | 59.642600 | 12.767405 | 82.175507 | 902.154327 | 130.432312 | FAIL | FAIL | FAIL | PASS |
| 1m | mixed | 3.566650 | 28.448825 | 10.380260 | 67.519623 | 1667.078731 | 240.875214 | FAIL | FAIL | FAIL | PASS |

## Resource v2

CPU one-core%, median dari median per-run; RAM bytes; peak lengkap dan DB/Bao/client ada di tables/v2-resources.csv. Nilai>100% CPU tidak otomatis salah.

| Skala | Mode | Skenario | DB CPU% | Client CPU% | Bao CPU% | DB RAM bytes | Client RAM bytes | Sampel |
|---|---|---|---|---|---|---|---|---|
| 100k | B | insert_member | 83.740000 | 131.825000 | 1.177500 | 2857226993.000000 | 72607744.000000 | 56 |
| 100k | B | list_page | 112.087500 | 133.025000 | 1.365000 | 2849979235.750000 | 73714688.000000 | 56 |
| 100k | B | mixed | 91.647500 | 132.025000 | 1.405000 | 2851321413.000000 | 72721408.000000 | 56 |
| 100k | B | read_by_email | 46.102500 | 128.675000 | 1.192500 | 2851321413.000000 | 73305088.000000 | 56 |
| 100k | B | read_by_nik | 45.322500 | 127.525000 | 1.207500 | 2847026446.000000 | 73291776.000000 | 58 |
| 100k | B | read_profile | 43.840000 | 129.350000 | 1.115000 | 2851321413.000000 | 73587712.000000 | 57 |
| 100k | B | update_contact | 127.802500 | 136.675000 | 1.575000 | 2854542638.500000 | 72954880.000000 | 56 |
| 100k | P | insert_member | 57.062500 | 121.225000 | 85.187500 | 2857763864.000000 | 69053440.000000 | 57 |
| 100k | P | list_page | 112.295000 | 115.300000 | 67.012500 | 2845415833.500000 | 69835776.000000 | 57 |
| 100k | P | mixed | 65.165000 | 120.800000 | 84.685000 | 2869575024.000000 | 69858304.000000 | 58 |
| 100k | P | read_by_email | 14.210000 | 122.725000 | 93.995000 | 2844878962.500000 | 69734400.000000 | 56 |
| 100k | P | read_by_nik | 14.230000 | 120.500000 | 94.325000 | 2842194608.000000 | 69992448.000000 | 56 |
| 100k | P | read_profile | 16.760000 | 120.150000 | 79.160000 | 2845952704.000000 | 70221824.000000 | 59 |
| 100k | P | update_contact | 233.637500 | 121.775000 | 69.262500 | 2857226993.000000 | 70048768.000000 | 56 |
| 1m | B | insert_member | 86.360000 | 134.050000 | 1.585000 | 3459596156.500000 | 76234752.000000 | 57 |
| 1m | B | list_page | 113.165000 | 133.175000 | 1.847500 | 3457448673.000000 | 78089216.000000 | 56 |
| 1m | B | mixed | 95.720000 | 130.350000 | 1.477500 | 3565091290.500000 | 77614080.000000 | 56 |
| 1m | B | read_by_email | 47.115000 | 127.575000 | 1.195000 | 3459059285.500000 | 77424640.000000 | 56 |
| 1m | B | read_by_nik | 46.627500 | 126.900000 | 1.202500 | 3458522415.000000 | 77777920.000000 | 56 |
| 1m | B | read_profile | 44.537500 | 126.225000 | 1.337500 | 3459059285.500000 | 77952000.000000 | 57 |
| 1m | B | update_contact | 132.552500 | 135.675000 | 2.060000 | 3458522414.500000 | 76726272.000000 | 56 |
| 1m | P | insert_member | 59.237500 | 120.975000 | 85.495000 | 3479460380.000000 | 72730624.000000 | 56 |
| 1m | P | list_page | 126.725000 | 115.225000 | 68.257500 | 3445100642.000000 | 75776000.000000 | 56 |
| 1m | P | mixed | 69.875000 | 117.850000 | 85.262500 | 3513014812.500000 | 76434432.000000 | 56 |
| 1m | P | read_by_email | 14.500000 | 118.950000 | 94.685000 | 3445369077.000000 | 74065920.000000 | 58 |
| 1m | P | read_by_nik | 15.135000 | 120.425000 | 94.037500 | 3440268803.500000 | 75599872.000000 | 58 |
| 1m | P | read_profile | 17.305000 | 118.525000 | 79.865000 | 3446711254.500000 | 73595904.000000 | 57 |
| 1m | P | update_contact | 236.697500 | 117.250000 | 69.405000 | 3466575478.250000 | 73650176.000000 | 56 |

## Dependensi/SBOM

```json
{
  "python_declarations": 24,
  "npm_lock_entries": 114,
  "image_references": 2,
  "transitive_python_complete": false,
  "deployment_os_inventory_complete": false
}
```

Daftar lengkap deklarasi Python/entri npm ada di tables/dependencies.csv; tiga CycloneDX1.6 ada di appendix/sbom/. Ini bukan SBOM environment deploy lengkap atau sertifikat CVEbersih.
