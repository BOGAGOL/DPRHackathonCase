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

Setelah restart Windows, recovery tujuh tabel benar-benar dijalankan pada container
sementara: 33 pemeriksaan lulus melalui HTTPS backend dengan schema/toolkit A asli.
Akun dan sesi hasil restore bekerja; enam peran, scope record, kebijakan FIN, pencarian,
update kontak/bidx dan insert allocator tervalidasi. Hilangnya identitas OpenBao
menghasilkan 500 generik, lalu layanan dapat membaca lagi setelah identitas sah
diinjeksi ulang. Tamper dan retention tujuh tabel juga lulus. Bukti mesin pada
`evidence/backup/service-recovery-integration.json`; rangkuman empat test integrasi
di `evidence/recovery/verification.json`. Pengujian ini memakai 17 record buatan
sendiri dan bukan acceptance pada dataset resmi atau benchmark.

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

## Perbaikan dependency saat persiapan deploy — 28 Oktober 2026 WIB

npm ci di server melaporkan satu advisory high pada Zod4.3.6. Audit lockfile lokal
mengonfirmasi GHSA-mrhx-c7xc-m3w5 (konsumsi memori berlebih ketika memvalidasi
koleksi besar; versi terdampak <4.6.6). Zod dipin ke4.6.7 dan lockfile diperbarui;
tidak memakai npm audit fix --force atau perubahan npm global server.

Validasi lokal sesudah perubahan: npm audit melaporkan0 vulnerability, build
produksi Next/TypeScript lulus, Playwright13 skenario lulus. Evidence audit di
app/evidence/access-control/npm-audit.json; report UI diekspor ulang oleh runner.
Hasil audit adalah snapshot advisory dependency, bukan klaim keamanan seluruh aplikasi.

Untuk paket runtime lama9029b77 yang sudah diunggah: jalankan dari app/web,
npm install zod@4.6.7 --save-exact, kemudian npm run build. Perintah sudah diberikan
ke Zhafif. Kelulusan instalasi backend/server ada pada log pengguna; upgrade Zod
serta build server belum diklaim PASS sebelum hasil aktual diterima.
Rujukan: https://github.com/advisories/GHSA-mrhx-c7xc-m3w5 dan
https://github.com/colinhacks/zod/commit/a0ebf970f2d752e5f58527cd2942ff48be4f46bd


## A5/B4: interface analis terbaru — 28 Oktober 2026

Instruksi Alby/Delf melalui Zhafif dan CONTRACT 10.1/PR A #10 mengganti perilaku
analytics lama. Query hanya public.analyst_summary via analyst_user, proyeksi
3 kolom dan bind parameter. Count >=5 (juga predicate pertahanan B), total selalu
null. Kelompok kecil tidak dikirim sama sekali termasuk labelnya. Tidak ada
placeholder <5 atau fallback per-record/role/decrypt. Filter cohort anggota lama
422 eksplisit; dimension/value memilih hanya marginal yang sudah dirilis.

DTO Python/TypeScript, form UI, fixture kedua mode, dan probe integrasi diselaraskan.
Setup plain baru/disposable menghasilkan marginal ekuivalen; tidak dijalankan ke
pg-dpr existing. Readiness tidak menerima evidence pre-A5 sebagai pengesahan versi
baru. Bukti historical baseline/protected tetap disimpan, bukan diubah menjadi PASS
A5. SHA provenance profile/format ciphertext tidak diubah oleh B.

Validasi final: pytest 328 lulus, 1 skip (swap ciphertext tidak berlaku pada plain),
termasuk 64 kasus analytics dua mode dan 2 gate readiness A5; Next production build
lulus; Playwright 14 lulus, termasuk filter marginal, empty state, dan escaping XSS
label yang dirilis. Evidence hanya status/metadata, bukan nilai anggota/rahasia.
Empat script setup/probe berubah juga diperiksa parse; integrasi PG18/OpenBao baru
belum dijalankan pada revisi ini. Mesin ini menyediakan PG17 native, bukan PG18;
tidak ada startup Docker, migrasi, SQL upgrade, atau akses VM dalam pekerjaan ini.

Panduan rilis: app/docs/DEPLOY_A5.md. Source yang diubah hanya app/. Paket VM
mengikutsertakan dependensi A5 yang sudah merged tanpa mengubah source A. Terapkan
SQL melalui infra.protected.analyst hanya pada protected_734 VM saat maintenance,
bukan migration prepare/full provisioning. Jangan menerapkan perubahan pada laptop
Delf/pg-dpr atau database benchmark selama benchmark berlangsung. Deployment A5 VM,
acceptance enam akun pasca-upgrade, sertifikat renew dry-run, dan systemd tetap
pekerjaan berikutnya, bukan PASS dari unit/browser mock.


## UI filter analytics — 28 Oktober 2026

Menindaklanjuti screenshot Zhafif: panel menempel pada tepi dan tombol terlihat
seperti teks. Penyebab pada revisi A5 B: form tidak mempunyai padding isi; class
btn-primary/btn-secondary tidak terdefinisi, sedangkan komponen Button shared memakai
button/button-primary/button-outline. Gunakan komponen shared itu, bukan alias CSS.

Panel mendapat padding 24px desktop/20px mobile, grid dua kolom yang bertumpuk pada
<=640px, tindakan terpisah dengan gap 12px dan tinggi minimal 44px. Label eksplisit
htmlFor/id, focus keyboard terlihat, input label kelompok disabled sampai dimensi
dipilih. Terapkan adalah aksi utama hijau; Reset outline dan disabled saat tidak ada
filter. Kartu total kosong dan paragraf penjelasan berulang dihapus; satu kalimat
menjelaskan kelompok kurang dari 5 tidak ditampilkan. DTO/API A5 tetap total null.

Acuan desain yang dibaca: GOV.UK Button (hierarki tindakan dan teks singkat), GOV.UK
Spacing (ruang konsisten/responsif), W3C WAI Labeling Controls (label terlihat dan
asosiasi eksplisit). Ini penerapan prinsip, bukan klaim audit aksesibilitas lengkap.
https://design-system.service.gov.uk/components/button/
https://design-system.service.gov.uk/styles/spacing/
https://www.w3.org/WAI/tutorials/forms/labels/

Uji browser existing diperluas untuk regresi penyebab screenshot: padding dan ukuran
klik, primary button mempunyai background, reset, fokus keyboard, layout 320/390px,
serta tidak ada overflow horizontal. Screenshot lokal hanya fixture sintetis, di
app/web/.local/. Build produksi Next.js/TypeScript lulus dan 14 test browser lulus.
Preview desktop/mobile sudah diperiksa visual. Tidak ada backend, SQL, izin, scope,
crypto, atau database yang diubah oleh perbaikan UI.


## Penyederhanaan layar layanan — 28 Oktober 2026

Zhafif menandai empat elemen untuk dihapus: panel promosi login, kartu keamanan dan
footer Modul B di sidebar, indikator Sesi terautentikasi, dan catatan backend pada
halaman profil. Semua dihapus dari markup, bukan disembunyikan dengan CSS. Login
menjadi satu kartu terpusat dengan brand ringkas, username/password dan tombol masuk.
Footer umum juga diringkas ke copyright brand. Identitas/peran akun dan tombol Keluar
masih ada di header; posisi akun diratakan kanan setelah indikator sesi dihapus.
CSS banner/sidebar lama yang tidak terpakai dibersihkan, termasuk selector responsif.

Login/CSRF/session, policy backend dan navigasi sesuai role tetap menggunakan flow
sebelumnya. Patch hanya frontend. Build Next.js/TypeScript lulus; preview login
1280px/390px diperiksa visual dan 14 test browser lulus. Screenshot sebelum input
kredensial, hanya memakai API mock sintetis. Tidak ada perubahan DB atau deployment
langsung ke VM. Rilis memakai paket frontend yang diperbarui dan rebuild/restart web.

## Kit persiapan whitebox pentest — 28 Oktober 2026

Prompt revisi pengguna secara eksplisit meminta docs/deploy/PENTEST_BRIEF.md dan
scripts/deploy/reset_to_golden.sh di luar app/. Perubahan dibatasi ke file tersebut
dan helper deploy B; tidak mengubah source/tooling A/C, SQL A5 atau dataset asal.
Audit historis docs/team_status_20261028.md dibaca dari remote run/overnight-28okt;
statusnya mendahului rilis A5 dan deployment VM, bukan bukti terbaru VM.

Delapan pt accounts memakai Argon2id/random, operator scope disjoint5+5, dua owner
bound ke pengguna_bidx unik. Admin setup URL harus protected_734, endpoint sama dan
verify-full. Existing file/scope diverifikasi tanpa rotate/regrant; demo/member rows
tidak ditulis. Private credential file600 di private/service-b/pentest/pt-accounts.json,
peta UUID/legacy metadata terpisah tanpa password. Disable8 pt membersihkan sesi.

Reset memerlukan dua unit systemd DPR yang isinya sama dengan source review,
lokasi checkout fixed, container berlabel vm-demo, PG18 TLS dan metadata identitas
cluster/OID. Golden immutable dibuat saat app berhenti, ALLOW_CONNECTIONSfalse;
reset hanya DROP/CREATE protected_734. Audit ekspor allowlist ke private600 sebelum
stop dan sesudah stop; CONNECT ACL dipulihkan, count734/A5/FORCE RLS dan14 login
diverifikasi. Fail stop tidak memaksa start app setelah kegagalan CREATE.
Setting database kustom ditolak sebelum golden karena tidak ikut CREATE TEMPLATE.
Golden satu volume bukan backup bencana, kehilangan kunci Bao tidak dipulihkan oleh
golden. Freeze key deletion/rotation; old versions yang tetap tersedia masih valid.
Restore utama Alby; disable pt sesudah restore agar tidak kembali aktif dari golden.

Output operator VM: localhost5433/8200/8100/3443, Nginx80/443, UFW inactive, unit DPR0,
unknown localhost36577 dikeluarkan dari scope. Cloud SG/iptables belum diverifikasi.
Operator telah mengupload kit melalui sesi SSH miliknya dan menjalankan provisioning,
install unit, A5 verify, inventory, create golden dan satu reset; semua PASS.
Laporan diunduh melalui SCP ke cache lokal dan disimpan terpisah sebagai vm-*.json.
Inventory nyata: PG18.6/Python3.12.3/Node24.22.1/Nginx1.24.0; modeprotected target734,
migration_jobs validated734, verifiedTLS seluruh URL role, Bao2.5.5 unsealed policy
svc-app TTL5648s pada21:24:57WIB. Reset count734 dan14 login/policy/IDOR/A5 checks
true. Metadata audit7849 event diekspor sebelum DROP. Unit test tidak dipakai untuk
mengklaim hasil VM. Peta10 UUID/legacy dan8 akun dimasukkan ke brief.

Inventory sudo mengidentifikasi localhost36577 sebagai containerd; tat_agent.service
dan daemon OS/Ardi excluded. iptables INPUTACCEPT/FORWARDDROP/OUTPUTACCEPT, nft raw
menolak akses non-loopback ke127.0.0.1 ports5433/8200. Cloud SG tetap NOT VERIFIED.
Certificate Let's Encrypt YE2 aktif sampai4Nov09:03:49WIB. Private custody/renewal
end-to-end dan pentest penuh Delf bukan hasil kit. Jangan disable pt sebelum pentest;
disable terakhir sesudah restore. Frontend tidak diubah, npm build tidak diperlukan.

## Target clone benchmark API — 29 Oktober 2026

Permintaan Zhafif berdasarkan kendala benchmark Delf: app sudah membaca DATABASE_URL
tetapi allowlist nama membuat clone api_* ditolak; C memakai swap nama original.
Review sumber/evidence commit10e4cc8 juga menemukan k6 trust-store dan cleanup conhost;
keduanya milik C. Laporan historis tersebut menyatakan measured_runs0/restore_failed,
bukan keadaan live yang diverifikasi pada pekerjaan ini. Tidak ada recovery/retry DB.

Perbaikan B menambahkan DPR_BENCHMARK_DATABASE untuk satu exact api_ name (ASCII
lowercase/digit/underscore, maksimum63), terpisah dari recovery. Guard default tidak
dilonggarkan. Seluruh URL runtime harus clone/host/port sama, role minimal, verify-full
dan CA file. Startup mengecek metadata read-only, marker setup/mode, tanpa role/DDL
berlebih, tabel B lengkap dan owner/FORCE RLS protected. Tidak fallback ke original.

CLI schema memilih cabang dari MODE untuk clone, memeriksa target/tabel anggota/TLS,
memberi CONNECT database dan USAGE schema kepada tiga role runtime serta marker setup.
CLI provision kedua mode memakai URL admin clone yang terverifikasi; akun existing
tetap ditolak, password random Argon2id di direktori privat per clone. Marker tidak
membuktikan integritas atau asal data: checksum/OID/HBA/cleanup tetap A/C.

Perubahan hanya app/. Repo utama sedang merge modul lain, sehingga pengerjaan di
worktree terpisah fix/service-b-benchmark-targets. Index/merge utama tidak disentuh.
Tes backend437 passed/1 skipped, termasuk47 tes target baru; fixture sintetis dan
mock metadata. Koneksi native clone/PostgreSQL18, provisioning/live benchmark dan
performa: NOT TESTED. Source C, target performa, dataset dan VM demo tidak diubah.
Handoff app/docs/BENCHMARK_CLONES.md menjelaskan env runner, CA file, origin, role,
TLS/HBA dan perlunya verifikasi recovery lama sebelum eksperimen baru.

## Upgrade dependency — 29 Oktober 2026

Permintaan eksplisit Zhafif mencakup requirements lintas modul, merge/push main,
VM dan regenerasi SBOM. Pekerjaan dilakukan di worktree terpisah; checkout pengguna
serta arsip untracked tidak disentuh. Integrasi a8adeb6 dengan main74f6205 bersih.
Pytest first-party menjadi9.0.3 (infra/toolkit rentang>=9.0.3,<10); cryptography
app/toolkit/infra dan prototipe>=50.0.2,<51; benchmark/verify50.0.2. Referensi buku
historis tidak diubah. Prototipe apps/api hanya deklarasi dependency, belum diuji.

Environment baru Python3.12: cryptography50.0.2, pytest9.0.3, pip check bersih;
toolkit108PASS/1SKIP, shared vectors8PASS, app437PASS/1SKIP. Skip integrasi opt-in;
ini bukan pentest atau benchmark. Laporan lokal di app/evidence/access-control/.
VM sebelum upgrade dikonfirmasi operator:46.0.7/9.0.2, dua service active; source
berasal dari arsip tanpa .git sehingga commit awal tidak diketahui. Deployment
memakai arsip rilis terverifikasi dan backup untuk rollback, bukan git pull palsu.
Status VM dan audit/SBOM masih PENDING sampai laporan nyata diterima. Jangan
restart PG/OpenBao, memprovision akun, merotasi kunci atau reset database.

## Dependency release — hasil VM dan SBOM terkonfirmasi

Main merge4fdd7aa dipush; VM memakai arsip source terverifikasi159file karena
instalasi existing tanpa Git. Commit awal null/unknown; commit_after adalah
identitas manifest rilis, bukan klaim git checkout atau penggantian build frontend.
Selesai29Okt11:41:01WIB: crypto46.0.7→50.0.2, pytest9.0.2→9.0.3, pip checkPASS,
dpr-api/dpr-web active. Smoke sebelum dan sesudah65/65 pada14akun; rollback tidak
diperlukan/dijalankan. Backup kode dan venv persis disimpan privat di VM.
PG/OpenBao tidak direstart; tidak provisioning akun, reset database atau rotasi kunci.

SBOM docs/sbom diregenerasi dari main4fdd7aa pada venv laptopPython3.12.10. Tiga
pip-audit requirements: app0/31dependency, benchmark0/22, infra0/16; skipped0.
Npm audit package-lock:0finding. Ada9JSON SBOM/audit; hash/tool/version/scope di
app/evidence/access-control/dependency-upgrade-sbom-20261029.json. Inventory
Windows app+infra+toolkit+audit tools bukan dump seluruh dependency VM; ranged
requirements BOM merekam deklarasi, environment BOM merekam versi terpasang.
VM siap diserahkan ke pentest Delf; hasil upgrade/smoke bukan kesimpulan pentest.

## F-01 — KTP unik, 29 Oktober 2026

Instruksi Zhafif menetapkan satu no_ktp non-NULL hanya satu record anggota. Tambah
sql/protected/04_identity_unique.sql, unique index bidx global/nondeferrable tanpa
plaintext, penolakan duplikat sebelum DDL dan verifikasi indeks existing agar tidak
salah menerima indeks nonunique/partial. NULL sumber tetap dapat berulang; tidak
mengubah format v1, normalisasi toolkit, ciphertext atau sumber734. Email/pengguna
belum memiliki aturan bisnis unik eksplisit sehingga tidak ikut diberi unique.

API menangkap hanya unique violation indeks KTP yang diharapkan, rollback sebelum
audit denied, balas409 generik tanpa ID/nilai/bidx. Integrity error lain tetap503.
Form POST menormalisasi digit/spasi/titik/tanda hubung sebelum validasi14/16digit;
nol awal dipertahankan. Plain API cek atomik dengan advisory transaction lock
per identitas pada PG, tanpa mengubah schema/data baseline milik C. Proteksi
persistensi terhadap semua writer ditegakkan pada protected; raw SQL baseline
bukan jalur layanan dan tidak mendapatkan constraint baru.

Tes482PASS/3SKIP, termasuk9native PG18 pada cluster disposable bertanda khusus:
request HTTP bersamaan menghasilkan201+409 dan search1, konflik tetap ditolak
meski record tersembunyi oleh RLS, migrasi fail closed/idempotent dan NULL terjaga.
Skipped: satu integrasi existing opt-in dan dua kasus RLS yang tidak berlaku plain.
Uji native memakai transport lokal disposable dan crypto test double; tidak mengaku
menguji TLS/OpenBao nyata lewat test tersebut. Evidence VM masih PENDING.

Reset golden lama sekarang memasang ulang indeks F-01 sebelum start aplikasi;
kegagalan migrasi menjaga service berhenti. Golden tidak dimodifikasi. Restore
backup lama Modul A juga harus menerapkan SQL04 sebelum membuka write API kembali.
Penerapan VM yang diminta: simpan metadata/audit, reset golden resmi, pasang SQL04
serta kode, restart hanya dpr-api/dpr-web dan smoke65. Akun pt tetap aktif sampai
retest Delf; disable paling akhir. Baseline benchmark/hasil historis tidak diubah.
