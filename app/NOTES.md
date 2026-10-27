# Catatan implementasi Modul B

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
