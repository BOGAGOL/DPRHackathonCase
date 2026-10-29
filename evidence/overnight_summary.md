# Kelanjutan 28 Oktober 2026: seluruh gerbang yang diminta PASS

pg_stat_statements diaktifkan dengan restart yang disetujui; extension pada empat
DB, workload role tanpa grant monitoring tambahan. Count kelima DB dan TLS
apply/verify/matriks (a)-(d) PASS, OpenBao tetap unsealed. Protected_734 belum
tersedia dan tidak diklaim telah diuji. Hanya B-P-P-B dengan konfigurasi baru
kelak boleh dibandingkan langsung; baseline awal tanpa extension dipertahankan.

Adapter protected toolkit A: gate baca 1000 kunci berbeda per skenario per skala,
8000 request/106000 baris hasil dibandingkan, 0 mismatch, db_time terukur terpisah.
Review update mengurangi unwrap menjadi satu; unit dan probe rollback/profile
nyata ulang yang terbatas PASS pada kedua skala. Target absolut +5ms baca/+10ms
tulis/mixed sudah commit/push 8c09a25 (13:37:47 WIB), ledger menyimpan semua entri.
Rasio 1.5x/P02/P03 tetap. Tidak menjalankan benchmark B-P-P-B atau benchmark lain.

Scanner v1.2 DB + dump protected_100k PASS. Delapan skenario leakage 100k/1M PASS:
ESCE AEAD no-key=0%, PII~83.67%, FIN~16.33%, search-kamus-lengkap~12.24%; DIE
no-key=0%, dengan kemampuan kunci/HMAC=100%. Domain terlarang ditolak; FIN masih
mengungkap identifier finansial/nama_rekening, sehingga bukan identitas global nol.
Ketiga token simulasi dicabut dan lookup-self ditolak 403. Tidak ada token root
pada proses attacker. Dump/ledger/kunci tetap privat di luar repo.

Residual REF+age_band+pola NULL, 41 kombinasi per populasi: min k full100k=136,
full1M=1362, source734=1, synthetic100k=135/synthetic1M=1361. Angka populasi penuh
terpengaruh pola sintetis berulang; tidak menjamin anonimitas subset sumber.
Ciphertext quasi candidates pada output scanner mentah tidak dijadikan bukti
re-identifikasi. Tabel before_after.csv 88 baris; CSV before lama diarsipkan.

Test komponen: scanner 193 PASS/1 SKIP opsional; verify/benchmark/datagen 111 PASS;
test fokus setelah review PASS. Masalah collection lintas folder dicatat, suite
final dipisah. Checksum penuh source734 dan kedua baseline cocok generation
setelah probe terakhir; count protected tepat dan principal sementara dibersihkan.
Sisa disk akhir sekitar 49.24 GiB (lihat byte aktual di evidence runtime/integrity).

Ringkasan mesin: evidence/overnight/resume_completion_20261028.json. Data leakage:
evidence/leakage/after_summary.json dan before_after.csv. API performance serta
P01/P01A/P02/P03 after tetap BELUM DIUJI sampai instruksi benchmark terpisah.

---

Laporan terdahulu berikut dipertahankan sebagai riwayat, bukan status terkini.

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
# Pembaruan kelanjutan 28 Oktober 2026, 13:15 WIB

Pemulihan PostgreSQL/OpenBao PASS, unsealed dan Transit siap; token svc-app dan
svc-migration baru TTL 4 jam tersimpan di luar repo. Count read-only kelima DB
sesuai 734/100000/1000000/100000/1000000, TLS verify-full aktif. Origin/main
ed88ecd (PR #5 b8e9998 dan PR #6) sudah digabung tanpa konflik melalui 0ba90db.
TLS final apply + verify PASS dan matriks (a)-(d) untuk kedua baseline/kedua
protected PASS; protected_734 belum dibuat dan tetap pending secara eksplisit.
Test regresi TLS: 19 PASS.

**Status terbaru: STOP prasyarat langkah 2.** shared_preload_libraries kosong;
pg_stat_statements belum aktif dan belum ada extension/view pada keempat DB.
db_time belum dapat diukur. Tidak mengubah konfigurasi preload, memasang
extension atau restart otomatis. Adapter/parity, target, verifikasi after dan
benchmark belum dilanjutkan. Migrasi 1M yang telah lulus tetap dipertahankan.
Evidence pemulihan: overnight/recovery_20261028.json; TLS: overnight/
tls_final_20261028/; hambatan: overnight/db_time_preflight_20261028.json.
Bagian berikut mempertahankan laporan sesi semalam sebagai riwayat.
