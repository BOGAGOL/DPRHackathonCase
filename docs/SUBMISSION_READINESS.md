# Audit kesiapan submit — 28 Oktober 2026

**Keputusan: BELUM SIAP SUBMIT.** Fondasi sistem dan banyak uji komponen sudah tersedia,
tetapi integrasi pemulihan layanan, pembuktian kebocoran, benchmark after, dan paket
pengumpulan belum lengkap pada `main` yang diperiksa.

Commit yang diperiksa: `ed88ecde71107ae3180b055eecefed3b9ad1f60b` (PR #6, integrasi aplikasi).
Perubahan terbaru `origin/main` sudah ditarik secara fast-forward ke branch kerja existing
`feat/crypto-migration`; local `main` juga sudah disamakan. Audit tidak mengubah source
implementasi, database, konfigurasi server, akun, atau kunci.

Bukti mesin audit: [submission-review-20261028.json](../evidence/readiness/submission-review-20261028.json).
Penilaian mengikuti PROJECT_CONTEXT, CONTRACT yang sudah diamendemen, TEAM_PLAN, prompt
modul, serta target F01–F05, S01–S09, P01–P03. Dokumen final di Drive belum diperiksa;
ketiadaan di Git tidak membuktikan ketiadaan di luar repository.

## Pembaruan recovery A/B setelah audit

R01/R02 sudah mendapat implementasi pada commit `8dfc985` dan `ea2b7a8`: layout backup
lima/tujuh tabel, sequence/grant, TLS restore, serta target aplikasi yang dipilih
eksplisit dan diperiksa saat startup. Regresi A **283 lulus / 8 skip**, B **286 lulus /
1 skip**; helper HTTPS **1 lulus**. Uji end-to-end Docker belum dapat berjalan karena
WSL host macet (`Unexpected WSL error`, context deadline exceeded). Jadi statusnya
**diimplementasikan + diuji komponen, integrasi live menunggu WSL pulih**, bukan
kelulusan pemulihan layanan penuh. Lihat [bukti verifikasi recovery](../evidence/recovery/verification.json)
dan [runbook cutover](../app/docs/RECOVERY.md). Temuan audit awal di bawah merujuk
commit ed88ecd; R03–R08 dan kesiapan submit keseluruhan belum dinyatakan selesai.

## Temuan yang menghalangi kesiapan

| ID | Prioritas | Temuan dan bukti | Tindak lanjut / pemilik |
| --- | --- | --- | --- |
| R01 | Tinggi | Backup hanya menerima tepat lima tabel A (`scripts/backup/postgres.py:17,33` dan manifest di `runner.py:93`). Setup B menambah `service_sessions` dan `service_member_bindings` (`app/scripts/schema.py:23`). Probe hasil katalog di memori membuktikan layout tujuh tabel ditolak dengan `unexpected_public_tables`. | **A + B:** dukung layout A dan A+B secara eksplisit, hitung seluruh tabel dalam manifest terautentikasi, validasi ownership/grant dan sequence, lalu ulang backup/restore/tamper/retention pada sistem terintegrasi. |
| R02 | Tinggi | Restore membuat `dpr_restore_<32 hex>`; `Settings.validate` B hanya menerima nama `protected_734/100k/1m` (`app/backend/service_app/config.py:31,38`). Probe konfigurasi mengonfirmasi penolakan, tanpa koneksi DB. `restore --with-openbao` sekarang membuktikan dekripsi sampel; evidence sendiri membatasi cakupan pada database, bukan pemulihan HTTP. | **A + B:** tetapkan cutover terkontrol yang menjaga TLS dan least privilege, lalu buktikan login, pencarian, baca, dan update melalui HTTPS setelah restore. Jangan menghapus allowlist atau guard TLS secara umum. |
| R03 | Tinggi | `verify/` saat ini hanya berisi NOTES, konfigurasi pengecualian scan, dan test konfigurasi. Belum ada `leak_sim`, `leakage_budget`, atau runner keamanan. Evidence leakage, `db-roles.json`, `secrets-and-logs.json`, dan `summary.json` belum ditemukan. | **C:** implementasikan dan jalankan skenario artefak nyata, ESCE/DIE/ELS/DBR, k-anonymity residual, role DB, dan scan rahasia repo/riwayat/log. Konfigurasi pengecualian bukan hasil scan. |
| R04 | Tinggi | `benchmark/__main__.py` hanya menerima adapter `plain` dan label `before`; adapter yang tersedia hanya plaintext DB. Ringkasan yang ada adalah baseline awal 100k dan 1M, bukan perbandingan protected atau API. | **C, dukungan A/B:** adapter protected/API, compare target P01–P03, scope akun dan hasil bisnis setara, dua blok B–P–P–B untuk setiap populasi yang dibandingkan, raw/resource dan median antar-run. Ulang timing backup protected sesuai metodologi. |
| R05 | Tinggi | Readiness B menyatakan PARTIAL: aplikasi pada dataset protected hasil migrasi dan benchmark API resmi belum diuji. Protected disposable lulus, tetapi bukan sertifikasi target 734/100k/1M. Evidence migrasi 1M A menyebut data buatan sendiri dan container sementara. | **A + B + C:** migrasikan `baseline_1m` resmi di laptop benchmark, lakukan decrypt-and-compare seluruh baris, lalu acceptance aplikasi/akses pada dataset target. Jangan memakai bukti disposable sebagai hasil benchmark resmi 1M. |
| R06 | Tinggi | Belum ditemukan laporan/slide final yang dilacak Git, `docs/evidence_index.md`, atau `docs/sbom/`. Diagram/threat model terkini dan paket reproduksi final juga belum terverifikasi. | **C dan tim:** siapkan laporan/panduan PDF 40–70 halaman, slide final, SBOM, indeks klaim ke evidence, diagram/threat model, panduan clone bersih, lisensi dokumentasi dan pernyataan AI. Bila sudah di Drive, periksa versi, akses, dan kesesuaian angkanya secara terpisah. |
| R07 | Sedang | Satu unit test benchmark membaca status charger laptop asli. Run normal gagal `Charger requirement not satisfied`; test yang sama lulus ketika sensor baterai dipalsukan sebagai plugged-in di proses uji, tanpa edit source. | **C:** mock sensor di unit test agar deterministik; pertahankan pemeriksaan charger pada benchmark nyata. |
| R08 | Sedang | README root dan default pytest masih mengarahkan ke `apps/api`/lab PostgreSQL 17 lama. Aplikasi aktif sekarang ada di `app/`; instruksi baru tersebar di README modul. | **Tim:** tambahkan pintu masuk resmi untuk PG18 `pg-dpr:5433`, OpenBao TLS dan `app/`, beserta test per modul. Verifikasi dari clone bersih. Instruksi lama boleh tetap sebagai arsip berlabel jelas. |

R01 dan R02 adalah masalah integrasi yang dikonfirmasi melalui pemanggilan fungsi aktual
dengan input sintetis di memori, bukan uji Docker langsung. Tidak ada backup/data asli
yang diubah. Perbaikannya perlu test regresi terintegrasi; uji A dan B secara terpisah
tidak mencakup pertemuan kedua modul tersebut.

## Bagian yang sudah memiliki implementasi dan bukti

- **A:** OpenBao TLS, toolkit AEAD/AAD dan blind index, protection profile, role/RLS,
  migrasi resumable, backup terenkripsi streaming, tamper/retention, dan rotasi KEK.
  Bukti aktual development 734/100k dan bukti disposable 1M memiliki cakupan berbeda.
- **B:** satu aplikasi plain/protected, enam peran, pembatasan record/field, HTTPS,
  audit, AAD fail closed, adapter toolkit A, dan suppression analytics. Evidence protected
  disposable mencatat 93 pemeriksaan lulus; baseline100k mencatat 181 pemeriksaan.
- **C:** datagen 100k/1M seed42, scanner dengan evaluasi ground truth, benchmark
  baseline awal 100k/1M tiga run per skenario dan backup/restore baseline, termasuk
  pemeriksaan raw dan pengukuran resource. Ini belum membuktikan overhead proteksi.

Proyeksi REF per record pada `analyst_view` sesuai kontrak saat ini; catatan B tentang
aggregate-only merupakan usulan lintas tim, bukan otomatis pelanggaran kontrak.
Kebocoran REF, equality blind index, pola NULL, batas session-variable RLS, aplikasi
yang dikuasai bersama kemampuan decrypt, dan isi backup lama tetap perlu ditulis jujur.

## Pengujian sesi audit

Hasil final per proses dicatat pada JSON audit. Test dipisah per modul untuk menghindari
tabrakan nama test/conftest aplikasi lama, aplikasi baru, dan benchmark. Percobaan
awal B dengan `--import-mode=importlib` gagal mengimpor `conftest`; pengulangan memakai
konfigurasi dan working directory `app/` yang sesuai. Jangan menyebut percobaan awal
itu sebagai bug runtime aplikasi.

- Suite A: **261 passed, 7 skipped**; skip mencakup integrasi yang memerlukan layanan.
- Datagen: **25 passed**.
- Scanner: **193 passed, 1 skipped**.
- Benchmark + konfigurasi verify: **27 passed, 1 failed** pada run normal, karena R07.
  Isolasi satu test dengan sensor baterai mocked: **1 passed**; run normal tetap dicatat gagal.
- Backend B: **276 passed, 1 skipped** (450,85 detik).
- Root tests aplikasi lama: **32 passed, 1 skipped** (338,63 detik); tidak dipakai sebagai
  sertifikasi aplikasi aktif `app/`.
- Total enam suite: **814 passed, 10 skipped, 1 failed**, termasuk suite aplikasi lama.
  Rerun diagnostik satu test baterai tidak dihitung ulang dalam total tersebut.
- Frontend: `npm ci` lulus; **production build dan TypeScript lulus**.
  Tiga test proxy/navigasi/CSP lulus (6,4 detik). Test ini tidak memakai fixture browser;
  seluruh suite browser tidak diulang karena binary browser Playwright belum tersedia
  lokal. Evidence 13 test UI terdahulu tetap merupakan bukti historis, bukan run baru.

Docker Engine lokal tidak aktif saat audit. Integrasi PostgreSQL/OpenBao/HTTPS,
backup/restore/rotation live dan pengujian browser terhadap layanan nyata **tidak
diulang** pada sesi ini. Bukti live lama tidak diganti atau diklaim sebagai run baru.
Scan rahasia menyeluruh, vulnerability audit, dan reproduksi clone bersih juga belum
dijalankan. Suite Python memakai root `.venv` existing, bukan instalasi baru seluruh
pin environment B/C; versi terpasang dicatat di JSON audit. README/evidence historis dibaca dengan memperhatikan laptop, dataset, dan commit.

## Urutan penyelesaian

1. **A + B:** selesaikan R01/R02, lalu sambungkan aplikasi ke protected hasil migrasi dan
   jalankan acceptance lengkap. Aktifkan Docker dan unseal OpenBao secara manual bila
   perlu pengujian lokal; jangan init ulang atau mengganti material kunci existing.
2. **C:** selesaikan runner keamanan/leakage dan adapter benchmark; siapkan migrasi 1M
   resmi bersama A. Samakan scope, DTO, parameter, dan populasi baseline/protected.
3. Jalankan verifikasi keamanan dan benchmark resmi pada laptop yang ditetapkan,
   dengan dataset tenang dan tanpa test berat/migrasi/demo bersamaan. Hasil gagal atau
   belum diuji harus tetap dilaporkan, tanpa mengubah target setelah melihat hasil.
4. Lengkapi paket R06/R08, jalankan scan final dan reproduksi clone bersih. Bekukan
   commit sumber serta angka laporan; verifikasi folder Drive dan akses pengumpulan.

Batas submit yang tertulis di PROJECT_CONTEXT: **29 Oktober 2026, 23.59 WIB**,
target internal sebelum 18.00 WIB. Audit ini tidak memverifikasi ulang ketentuan panitia
di luar dokumen proyek dan tidak melakukan pengumpulan atau mengirim pesan ke anggota tim.
