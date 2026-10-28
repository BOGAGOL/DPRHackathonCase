# Catatan implementasi Modul B

## Perbaikan recovery A/B oleh Alby — 28 Oktober 2026

Pengguna secara eksplisit mengizinkan pengerjaan kedua modul karena Zhafif berhalangan.
`DPR_RESTORED_DATABASE` menerima satu nama dpr_restore_<32 hex> yang sama dengan seluruh
URL runtime, hanya MODE=protected. Guard role dan TLS verify-full tetap berlaku.
Startup menggunakan app_user read-only untuk memeriksa nama/role/TLS, provenance marker
restore yang telah dipublish A, tepat tujuh tabel dan owner/FORCE RLS anggota.
Marker saja tidak membuktikan integritas arsip; pemeriksaan HMAC/SHA/AEAD adalah tugas
restore A. Kredensial admin/setup tidak diperlukan atau diteruskan ke aplikasi.

Setup B yang idempoten menambah SELECT pada service_legacy_id_seq kepada backup_user,
tanpa memberikan UPDATE sequence (setval), DDL, atau akses OpenBao. Sequence existing
tidak di-reset. Restore mempertahankan akun/scope/binding/sesi dan allocator, sehingga
tidak perlu provision ulang akun setelah cutover. Backup data-only lima tabel lama
tidak dianggap backup layanan B lengkap dan ditolak oleh gate startup recovery.

Pengujian recovery memakai data buatan sendiri di PostgreSQL/OpenBao TLS sementara;
HTTPS backend membuktikan alur aplikasi. Ini tidak menggantikan benchmark resmi,
acceptance pada dataset hasil migrasi tim, atau bukti browser/frontend terpisah.

Pemilik: Zhafif. Platform: Windows PowerShell. Branch kerja: `feat/service-app`. Acuan mengikat: `AGENTS.md`, `docs/PROJECT_CONTEXT.md`, `docs/contracts/CONTRACT.md`, `docs/TEAM_PLAN.md`, dan `docs/ai-prompts/PROMPT_B_SERVICE_APP.md`.

## Batas perubahan dan penggunaan ulang

Kode layanan lama tetap berada di `apps/api` dan `apps/web`, tidak diubah. Implementasi Modul B memakai stack yang sama dalam `app/`: Python/FastAPI/Pydantic/SQLAlchemy/Psycopg/Argon2id serta Next.js/TypeScript/React/Tailwind. Kriptografi lokal lama di `apps/api/app/crypto.py` tidak disalin sebagai implementasi protected baru. Toolkit, migrasi, profile, infra, scanner dan benchmark milik A/C tidak ditulis ulang.

Tidak mengubah database sumber `postgres`. Tidak menjalankan generator, migrasi, truncate atau restore terhadap `baseline_100k` untuk menyelesaikan aplikasi. Uji mutasi harus memakai dataset baru yang seluruhnya sintetis atau rollback yang eksplisit, bukan source/baseline tim.

Hanya folder `app/` diubah pada pekerjaan ini. Karena itu evidence mesin default berada di `app/evidence/access-control/`; formatnya bisa disalin ke `evidence/access-control/` repository oleh koordinasi tim setelah diizinkan. Test hanya memakai data sintetis buatan sendiri, tidak menyalin isi dump panitia.

## Status dependensi saat audit — 27 Oktober 2026 WIB

| Dependensi | Hasil pemeriksaan |
|---|---|
| `baseline_100k` | Evidence C tanggal 26 Oktober mencatat 100.000 record dan validasi PASSED; ini bukan bukti koneksi database tersedia pada host saat ini. |
| PostgreSQL `pg-dpr` | Read-only Docker inspection pada host sesi ini: container `pg-dpr` tidak ada; tidak ada query ke source/baseline. |
| OpenBao/TLS infra A | Kode dan evidence disposable integration tersedia. NOTES A menyatakan lab utama belum initialized/sealed, serta TLS PostgreSQL belum dikonfigurasi. Status live host tidak dianggap sama dengan evidence historis. |
| `toolkit/dprcrypto` | Belum tersedia pada checkout saat audit. |
| `policy/protection_profile.yaml` | Belum tersedia pada checkout saat audit. |
| `docs/contracts/test_vectors.json` | Belum tersedia pada checkout saat audit. |
| Credential sesi | Tidak ada nama env DPR/DB/OpenBao/PG yang terdeteksi pada environment proses audit. Tidak ada nilai credential dicetak/dibaca untuk laporan. |

Tidak ada fallback dari MODE=protected ke MODE=plain, tidak ada fallback plaintext saat decrypt gagal, dan tidak ada penurunan `sslmode` untuk mengejar demo. Tanpa toolkit/role/schema/PKI yang diperlukan, integrasi target tetap NOT TESTED atau gagal tertutup.

## Identitas record pada API dan database

Kontrak bagian 4 mewajibkan PK internal protected berupa UUIDv4 acak dan menyimpan `legacy_row_id` untuk pemetaan baseline. Kontrak tidak menetapkan tipe public locator API secara eksplisit. Implementasi B memakai `anggota_id` API sebagai string locator legacy yang sama di kedua mode agar workload C dan perbandingan DTO dapat menunjuk record bisnis yang sama. MODE=protected memetakan locator itu ke `legacy_row_id`; UUIDv4 internal tidak diubah dan tetap dipakai oleh toolkit untuk AAD persis kontrak.

Konsekuensi: locator legacy dapat dienumerasi; ia bukan kontrol keamanan. Semua akses tetap memerlukan authorization per record/field. Tim A harus mempertahankan pemetaan dan menyediakan alokasi `legacy_row_id` untuk insert protected; C harus memakai locator/API mapping yang sama saat membandingkan hasil. Jika tim memilih public UUID sebagai gantinya, siapkan mapping bersama sebelum mengubah kontrak API dan workload. Ini keputusan API sementara yang didokumentasikan, bukan perubahan format ciphertext.

## Kontrak integrasi yang dibutuhkan dari Modul A

Backend Python hanya mengimpor `dprcrypto` melalui factory yang dikonfigurasi. B tidak mengimplementasikan AES, nonce, AAD, HMAC, pembungkusan DEK, atau client Transit baru. A perlu menyediakan adapter yang dapat:

1. Menghitung blind index untuk `no_ktp`, `email`, `pengguna` sesuai normalisasi dan domain label kontrak.
2. Batch unwrap DEK PII/FIN per halaman, lalu mendekripsi hanya field yang diminta policy B. Peran yang tidak berhak FIN tidak meminta DEK FIN.
3. Mengenkripsi field baru/berubah dengan UUID dan `protection_version` record, mempertahankan NULL, lalu memperbarui blind index yang relevan.
4. Menyiapkan kedua wrapped DEK untuk insert, tanpa menyimpan DEK plaintext pada file/log/evidence.
5. Menghasilkan exception aman untuk tamper, swap record/kolom, key tak tersedia, TLS gagal, token invalid, dan format unsupported. B menerjemahkannya menjadi HTTP 500 generik serta audit metadata; tidak ada body error Transit diteruskan.

Factory awal yang diharapkan: `DPR_CRYPTO_FACTORY=dprcrypto:create_service`. Interface Python persisnya harus dicocokkan saat paket A tersedia; method yang belum ada tidak disimulasikan sebagai dukungan produksi. Test double boleh dipakai hanya pada tes, dengan label yang membedakannya dari bukti kriptografi nyata. `test_vectors.json` milik A wajib digunakan untuk validasi interoperabilitas ketika tersedia.

## Binding akun anggota pada database protected

Provisioning protected tidak menyimpan salinan plaintext kolom `pengguna` dalam tabel akun. Hanya akun `anggota` menyimpan binding `bidx:v1:<hex HMAC pengguna 32 byte>` dari toolkit A. Role lain menyimpan ID akun acak sebagai principal, bukan identifier anggota. Predicate SQL protected membandingkan bytes blind index tersebut. `SET LOCAL app.principal` menerima hex tanpa prefix ketika binding protected; A perlu memakai encoding ini pada policy RLS target. Tidak ada salinan plaintext tersembunyi untuk mempercepat ownership/search. Raw binding pada mode protected hanya diterima pada fixture `Settings.testing` untuk uji parity yang berbagi tabel akun; CLI tidak mengekspos flag testing.

Hasil adapter diperiksa sebelum digunakan: DEK/index 32 byte, panjang batch sesuai input, blob versi 1 minimal 29 byte, wrapped DEK berformat Transit, dekripsi non-NULL harus string. Nilai `None` dari kegagalan driver tidak boleh berubah menjadi NULL/default atau hasil pencarian kosong yang tampak sukses. NULL sumber tetap NULL dan tidak didekripsi.

## Kontrol transport dan batas uji

Koneksi PostgreSQL aplikasi wajib `sslmode=verify-full` dan root CA eksplisit. HTTPS browser memakai sertifikat lokal dari Modul A melalui `TLS_CERT_FILE`/`TLS_KEY_FILE`; Next.js dan backend harus memakai origin/CA yang cocok. Sertifikat yang dipasang pada OpenBao tidak membuktikan TLS PostgreSQL atau HTTPS browser.

Bukti real PostgreSQL yang aman dapat dibuat memakai project Docker acak dan database disposable baru, sertifikat dari fungsi publik pembuat CA Modul A, credential acak, dan fixture buatan sendiri. Keberhasilan itu membuktikan jalur TLS/role/API pada lingkungan uji tersebut; tidak membuktikan baseline_100k milik tim sudah dapat dipakai atau OpenBao target sudah terintegrasi.

Matriks peran final B ada di `ACCESS_MATRIX.md`. Staff internal memiliki cakupan demo yang didokumentasikan; anggota dibatasi predicate SQL kepemilikan, analyst/auditor tidak memperoleh route record. Nama operator pada detail penuh mengikuti PROMPT_B, tetapi nama daftar dimasking.

## Bukti implementasi dan pengujian — 27 Oktober 2026 WIB

`app/scripts/integration_probe.py` dijalankan pada Docker Desktop menggunakan project acak, PostgreSQL 18 baru, database `dpr_b_test_*` baru, fixture buatan sendiri dan credential acak. Exit code akhir **0**, **122 pemeriksaan lulus**, `cleanup_passed=true`; ringkasan mesin: `app/evidence/access-control/postgres-tls.json`.

Batas bukti run tersebut:

- Native PostgreSQL memakai tanggal/integer dan identity seperti baseline tim; tidak hanya tipe text SQLite. `sslmode=verify-full` dipakai untuk tiga role runtime, CA salah ditolak, flag superuser/DDL/BYPASSRLS dibatasi.
- Policy forced RLS hanya dibuat pada tabel fixture disposable; anggota melihat satu record miliknya, ID lain ditolak, `app.principal` diset oleh API dan reset setelah transaksi. Ini bukan pengujian policy protected produksi milik A.
- API plain nyata diuji untuk enam peran, parameter pencarian berbahaya, DTO/masking, CSRF, PATCH, insert, analytics/audit dengan identitas DB terpisah dan metadata audit.
- Server Next HTTPS dan FastAPI HTTPS benar-benar dijalankan dengan cert temporer dari generator A. Node memverifikasi CA backend; API memverifikasi CA PostgreSQL. Browser Chromium memakai pin SPKI sertifikat uji, tanpa blanket `ignoreHTTPSErrors` atau global `NODE_TLS_REJECT_UNAUTHORIZED=0`. Pengujian browser memakai enam akun dan memeriksa cookie, CSP, storage, JSON mentah, exact lookup, update+restore, IDOR dan logout.
- Tidak ada credential pada argumen proses/hasil, tidak ada body/query pribadi di evidence, tidak ada source/baseline tim yang diakses. Hanya proses child yang dicatat dan volume project random milik probe dihentikan/dihapus.

Run awal probe memiliki satu false-positive canary pada fixture: nomor KTP berawalan nol kebetulan menjadi substring rekening yang memang diizinkan bagi finance. Fixture diperbaiki dengan prefix domain identifier yang berbeda, bukan dengan melonggarkan policy/masking atau menyembunyikan kegagalan. Evidence PASS berasal dari run baru yang lengkap, bukan mengedit hasil gagal menjadi lulus.

Hasil Python/UI terbaru diekspor tersendiri ke `app/evidence/access-control/`. Hasil historis 33 tes Python/5 browser aplikasi lama tidak digunakan sebagai bukti kepatuhan kontrak baru. Mode parity dengan crypto test double tidak sama dengan decrypt-and-compare terhadap paket/test vectors/live OpenBao A. **Integrasi `baseline_100k` pada server tim, protected live, grants/RLS target, dan benchmark API 100k tetap NOT TESTED** sampai target/kredensial/dependensi tersedia. `check_ready.py` sengaja mempertahankan status PARTIAL untuk integrasi tersebut.

Suite Python akhir: **222 passed, 1 skipped, total 223**, exit 0. Skip hanya swap ciphertext pada mode plain yang tidak berlaku; mode protected menguji swap dan audit kegagalannya. Suite UI: **12 passed**, build produksi dan TypeScript lulus. Bukti ini mencakup enam peran, DTO mentah, IDOR/BOLA, normalisasi lookup, update bidx, insert, batch unwrap/proyeksi minimal, session/CSRF/header/CSP, output provider yang invalid, binding opaque, dan guard runtime/setup. Report mencatat hash source tree serta status dirty ketika dijalankan agar hasil tidak keliru diklaim berasal dari commit base yang belum memuat kode baru.

## Pembaruan lab lokal Zhafif — 27 Oktober 2026 WIB

Status awal di atas merupakan riwayat sebelum lab ini dibuat. `local_lab.py` kini menyediakan
container persisten **pg-dpr**, PostgreSQL **18.6**, port lokal **5433**, TLS wajib dan sertifikat
dari generator A. `postgres` diinisialisasi satu kali pada instance baru dengan 734 record dari
`sql/baseline/02_data.sql` commit main **cf2d2ccd786066ad9ea3c56ec2999987feda73ac**. Setelah itu,
tidak ada perubahan pada sumber. Instance/volume yang tidak memiliki label kepemilikan B ditolak;
skrip tidak mencoba mengadopsi atau mereset infrastruktur orang lain.

Datagen C dijalankan tanpa mengubah kodenya: **100.000 baris, seed 42, 734 sumber + 99.266 sintetis**.
Tujuan report generator diarahkan ke `app/` melalui adapter script B agar batas kepemilikan folder
tetap dipatuhi. Validasi C lulus dan checksum seluruh baseline identik dengan evidence C yang
sudah tersimpan di repo. Semua password/CA signing key/akun demo berada di storage privat luar Git
dengan ACL utility A; hanya server TLS material dan password-file bootstrap dipasang ke container.

`baseline-100k.json` mencatat **181 pemeriksaan lulus**: enam peran, DTO mentah dan correctness field,
lookup, pagination 50 sampai halaman 2000, IDOR, PATCH, insert, analytics/audit, TLS tiap role,
penolakan CA salah/non-TLS, no-DDL/NOBYPASSRLS, RLS lokal deny-default dan reset principal.
Browser menguji Next HTTPS → API HTTPS → database verify-full, termasuk cookie/CSP/storage,
masking, pencarian dan pembaruan kontak. Kontak dan insert uji dipulihkan; checksum seluruh baseline
dan sumber cocok kembali. Metadata audit sengaja tetap tersimpan. Tidak ada benchmark bersamaan.

Setup ulang diuji dan lulus tanpa reimport/regenerasi/rotasi kredensial. Suite Python terbaru:
**243 passed, 1 skipped**, exit 0; hasil mesin diekspor ulang. Satu skip tetap kasus ciphertext
swap pada plain yang tidak relevan. UI mock suite sebelumnya 12 lulus; alur browser nyata terbaru
termasuk dalam 181 pemeriksaan di atas. Bug helper probe saat `AUTH_DATABASE_URL` tidak diisi
diperbaiki agar memakai database runtime default, dengan regression test. Run gagal awal disimpan
sebagai riwayat penjelasan ini; PASS berasal dari pengulangan lengkap sesudah perbaikan.

`check_ready.py` sekarang membaca bukti target 100k dan hanya menerima status PASS jika semua
pemeriksaan wajib ada serta bernilai true. Bukti parsial/palsu/failing tidak mengubah target menjadi
PASS. **MODE=plain baseline_100k lokal: PASSED. MODE=protected live dan benchmark API resmi: NOT TESTED.**
Readiness keseluruhan tetap PARTIAL. Toolkit/profile/test vectors A belum tersedia pada main yang
diperiksa; B akan menyesuaikan bridge saat API A tersedia. Format AAD UUID, locator legacy, dan
principal hex tidak diubah; lihat `docs/LOCAL_LAB.md` untuk tiga titik sinkronisasi A/B dan runbook.

Perubahan lanjutan tetap hanya `app/`. PR #1 disiapkan untuk review Alby; merge ke main menunggu
review anggota lain sebagaimana TEAM_PLAN, bukan dianggap sudah selesai dari bukti lokal saja.

## Integrasi setelah pull main b8e9998 — 28 Oktober 2026 WIB

Pembaruan ini menggantikan blocker toolkit belum tersedia dan asumsi principal hex pada catatan
historis di atas. Instruksi/kontrak/panduan migration serta perubahan A diperiksa sebelum edit.
Seluruh perubahan source, dokumentasi dan evidence tetap di app/. Tidak menjalankan migrasi A,
regenerasi baseline_1m, benchmark C, atau perubahan SQL/toolkit/infra bersama.

Keputusan implementasi:

1. Adapter memanggil API publik A aktual (OpenBaoClient, KeyManager, BlindIndexer, encrypt/decrypt).
   Default public-v1, alias lama hanya kompatibilitas konfigurasi; tidak ada factory arbitrer.
   KeyManager tanpa cache agar revoke token menyebabkan operasi berikutnya gagal tertutup.
2. Protected menggunakan app_users/access_scope/audit_log A; B menambah hanya sessions, binding
   anggota, dan sequence legacy locator. app.principal adalah UUID akun. Anggota memerlukan
   binding bidx DAN scope; staff juga memerlukan scope. PATCH harus update, bukan sekadar read.
3. Insert tanpa RETURNING mengikuti trigger scope A. Sequence B dialokasikan dari MAX seluruh
   dataset saat trusted setup pertama, tidak dari subset RLS runtime. Tidak mereset sequence
   existing. Sesudah migrasi tambahan, admin perlu koordinasi alokasi sebelum insert B dibuka.
4. Audit hanya mengirim kolom yang diizinkan A; actor/role berasal dari trigger. Error dekripsi
   menjadi 500 generik dan audit error, tanpa plaintext fallback atau nilai pencarian.
5. Analytics menerapkan filter SQL berparameter sebelum suppression. Count1–4 menjadi "<5";
   total/sibling tertentu null untuk secondary suppression. Frontend tidak menerima angka asli.
   Count5 tetap 5 bila tidak menjadi secondary suppression. DTO count menjadi number|"<5"|null.
6. Python3.12.10 dipakai dalam app/.venv, karena toolkit A memerlukan minimal3.11. Versi utama
   diuji: FastAPI0.134.0, SQLAlchemy2.0.47, Pydantic2.12.5, Psycopg3.3.3, cryptography46.0.7,
   Starlette1.10.0, pytest9.0.2. Ada warning deprecation TestClient/httpx; bukan test failure.

Hasil run terakhir (bukan perkiraan):

- Pytest: **276 passed, 1 skipped**, total277, exit0. Skip ciphertext swap pada plain yang tidak
  berlaku; protected swap benar-benar diuji. Raw JUnit lokal, ringkasan disanitasi diekspor.
- Next production build: lulus. Playwright UI mock: **13 passed**, termasuk rendering <5/null
  dan filter kombinasi. Evidence UI tidak diklaim sebagai bukti database/crypto.
- Baseline100k existing: **181 checks PASS**, six-role HTTPS browser/API, checksum baseline dan
  source kembali sama setelah mutasi uji. Datagen tidak dijalankan ulang.
- Protected disposable: **93 checks PASS**, actual schema/toolkit A + PG18/OpenBao TLS, AAD swap,
  revoke token, record scopes, akun/audit A, insert trigger, PATCH+bidx, six-role HTTPS browser.
  Cleanup project Docker acak PASS. Ini fixture sintetis kecil, bukan migrasi dataset target.
- Shared vectors A: **8 checks PASS**, evidence dari CLI A. AAD/blob/tamper/record swap/column swap/
  nonce sample/normalisasi/bidx. Tidak mengimplementasikan kripto kedua di B.

Run awal Python3.12 dalam sandbox Windows gagal akses direktori temporer; run akhir memakai
izin eksekusi yang sesuai dan menghasilkan JUnit baru. Probe protected pertama menemukan
missing dependency sebelum membuat resource; dependencies dipasang, lalu run penuh lulus.
Kegagalan awal tidak disembunyikan sebagai PASS; evidence final berasal dari run ulang nyata.

Keterbatasan/handoff: local pg-dpr hanya postgres dan baseline_100k. Protected_734/100k/1m hasil
migrasi lokal dan benchmark API resmi masih **NOT TESTED**. Tidak ada klaim rows_compared1M.
Readiness tetap PARTIAL meskipun protected disposable lulus. A masih perlu membatasi akses
langsung analyst_user ke agregat; schema saat diperiksa mengekspos REF per record melalui view.
Small-cell suppression B tidak menjamin perlindungan terhadap seluruh query differencing
lintas filter/waktu. Samakan scope akun/workload sebelum benchmark plain vs protected C.
Panduan PowerShell lengkap: docs/INTEGRATION_A.md. PR1 sudah merged; perubahan ini PR lanjutan,
merge ke main tetap memerlukan review anggota lain sesuai TEAM_PLAN.
