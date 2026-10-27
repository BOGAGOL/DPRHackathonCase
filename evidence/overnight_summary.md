# Ringkasan overnight - 28 Oktober 2026

**Status akhir: BERHENTI pada gerbang 2; adapter protected belum tersedia.**

| Langkah | Hasil |
|---|---|
| 0 - merge | PASS; union lengkap verify/NOTES.md diizinkan pengguna, commit 07fbf4a |
| 1 - migrasi protected_1m | PASS; passed=true, rows_compared=1000000 |
| 2 - parity adapter | FAILED_PRECONDITION; benchmark/adapters/protected.py belum ada |
| 3 - amandemen target | Belum dijalankan |
| 4 - scanner/leakage/residual after | Belum dijalankan |
| 5 - benchmark B-P-P-B | Belum dijalankan; 0 run |
| 6 - evidence dan laporan | Disimpan pada branch run/overnight-28okt; tanpa merge ke main |

## Angka migrasi aktual

- Run termasuk validasi penuh dan pencabutan token: **2525.540631 detik (42.092 menit)**.
- Sesi keseluruhan termasuk token/prepare/check: **2540.822885 detik (42.347 menit)**.
- Validasi membandingkan seluruh 1.000.000 baris dan semua field, termasuk NULL/REF/age_band/blind index.
- Token svc-migration dan svc-app BARU TTL 14400 detik dipakai, tanpa root pada migrator. Token migrasi sudah dicabut dan ditolak (403); migration_user kembali NOLOGIN.
- Ukuran baseline_1m: **825194175 byte (786.97 MiB)**.
- Ukuran protected_1m: **2210617023 byte (2108.21 MiB)**; rasio **2.679x**.
- Sisa disk pada completion: **54.44 GiB**.
- Source postgres, baseline_100k dan baseline_1m: jumlah baris, OID, relfilenode, counter insert/update/delete dan waktu postmaster tetap sama.

## Lingkungan dan gangguan AC

- AC sesi migrasi terkonfirmasi: **2538 sampel, 0 sampel bukan AC, 0 event Kernel-Power AC=false**. Waktu WIB sekitar 01:11:26-01:53:47.
- Insiden sebelum sesi: **00:58:21,876-00:58:54,603 WIB**, 32,73 detik; rangkaian saat itu berhenti pada konflik merge, sehingga 0 run terdampak/diulang.
- Supervisor memantau AC dan disk >=10 GiB; tidak ada restart container atau perubahan baseline.

## Penyebab berhenti

Branch feat/verify-bench hanya menyediakan adapters/__init__.py dan adapters/plaintext.py. Tidak ada protected.py atau ProtectedAdapter. Karena itu 1000 kunci per skenario baca pada kedua dataset **belum diuji** dan db_time **belum terukur**. Ini kegagalan prasyarat gerbang, bukan bukti hasil bisnis berbeda. Tidak ada angka parity/performance yang dikarang.

Aturan pengguna mewajibkan STOP pada gerbang gagal tanpa retry otomatis. Tidak membuat adapter/perbaikan otomatis, tidak mengubah target, dan tidak melanjutkan verifikasi after/benchmark. Target dan hasil baseline terdahulu tetap dipertahankan.

Kelanjutan memerlukan implementasi adapter protected dan instrumentasi db_time dengan test, lalu instruksi melanjutkan gerbang 2. **Jangan hapus atau membuat ulang protected_1m yang sudah tervalidasi.**

## Evidence dan pemeriksaan

- [Validasi 1M](migration/validation-protected_1m.json)
- [Sesi dan durasi](overnight/migration_1m/session.json)
- [Completion dan keutuhan source](overnight/migration_1m/completion.json)
- [AC/Kernel-Power](overnight/migration_1m/power_verification.json)
- [Gerbang adapter](benchmark/adapter_parity.json)
- [Union merge](overnight/gate0_resolution.json)
- [91 unit test sesuai lingkungan modul](overnight/merge_verification.json)

Collection gabungan awal salah memilih venv benchmark untuk verifier (Jinja2 tidak tersedia); suite dijalankan dalam lingkungan modul yang sesuai: 67 benchmark/datagen + 24 verify lulus. Collection error tetap dicatat, bukan diklaim sebagai test lulus. Tidak ada pengulangan gerbang bisnis. Laporan terdahulu diarsipkan pada overnight/history/.
