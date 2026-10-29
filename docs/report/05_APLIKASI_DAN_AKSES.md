# 5. Backend, frontend dan bukti kewenangan

## Implementasi dan alur request

FastAPI/Pydantic/SQLAlchemy backend, Next.js/React frontend, PostgreSQL 18 dan
adapter dprcrypto. MODE=plain/protected memilih repository yang berbeda dengan
operasi bisnis sama; SQLite/FakeCrypto hanya fixture test, bukan deployment.
Settings produksi menolak engine/role/database di luar allowlist, origin bukan
HTTPS, CA tidak ada atau PG tidak verify-full. Auth/analyst/auditor/data pada mode
protected wajib menunjuk target yang sama. Credential tidak dikirim ke browser.

Alur: cookie sesi → lookup token hash/expiry/user active → role action → transaksi
principal → scope record → proyeksi field minimum → decrypt domain yang diperlukan
→ masking sesuai policy → DTO allowlist → respons no-store. RLS bukan satu-satunya
lapisan; query repository juga memasukkan kondisi scope.

## Enam role aplikasi dan field yang sebenarnya

| Role | Record/action | Detail yang dirilis |
|---|---|---|
| operator | List/search/detail record terassign; update kontak jika ada permission update | nama lengkap pada detail; no_ktp/email/handphone/telpon_jakarta/telpon_daerah dimasking; nama pada list dimasking |
| privileged_officer | Scope terassign, update kontak, insert dengan izin insert eksplisit | Semua source fields selain4 FIN; bukan otomatis decrypt finansial |
| finance_officer | Baca record terassign; bukan edit kontak/insert | nama/no_ktp masked; rekening/nama_rekening/npwp/kode_bank/nama_bank/nama_kppn sesuai hak finance |
| analyst | Hanya analytics; tidak list/detail/search/anggota/audit | Lima marginal rilis, total=null, count>=5; tanpa per record |
| auditor | Hanya audit metadata; tidak data anggota/analytics | actor/role/action/decision/field class/request id/waktu menurut DTO |
| anggota | Record miliknya sendiri, update kontak dengan scope update | Field PII/REF seperti privileged, tanpa FIN |

Ini role aplikasi, bukan nama login PostgreSQL. assignment scope sintetis dapat
berbeda antar deployment. Jangan menyimpulkan privileged_officer bisa membaca
semua record atau bahwa anggota mendapat data keuangan karena pemilik record.

## Endpoint penting

| Endpoint backend | Tujuan/kontrol |
|---|---|
| GET /health/live, /health/ready | Liveness/dependency readiness; bukan kebocoran konfigurasi/key |
| GET /auth/csrf; POST /auth/login | CSRF double-submit, username/password, Argon2id, rate limit |
| GET /auth/me; POST /auth/logout | Identitas sah, revokasi sesi dan pembersihan cookie |
| GET /anggota | Paging50 dan proyeksi id/nama, scope sebelum hasil |
| GET /anggota/search | Exact no_ktp/email, input terbatas, bidx pada protected |
| GET /anggota/{business_id} | Field allowlist/record scope, bukan UUID storage sebagai URL |
| PATCH /anggota/{id}/kontak | Hanya email/handphone, CSRF, scope update, reencrypt/bidx |
| POST /anggota | privileged + insert scope, record/key baru, validasi semua input |
| GET /analytics/summary | analyst, SQL aggregate-only, filter marginal rilis |
| GET /audit | auditor, metadata minimal dan paging |

Prefix same-origin /api pada frontend bukan bagian path backend langsung.
Tambahan id/protection/wrapper/bidx/timestamp internal tidak boleh lolos DTO.
Input extra fields ditolak, tanggal/phone/email/identifier diperiksa. Sanitasi
validasi tidak boleh mengubah data migrasi sumber diam-diam.

## Sesi, XSS, cache dan audit

Password Argon2id. Token sesi CSPRNG; hash token disimpan pada sessions, bukan
password hash dipakai sebagai cookie. Cookie sesi Secure/HttpOnly/SameSite=strict,
CSRF cookie/header terpisah diikat hash sesi. TTL default900s (range60–1800).
Login/logout/mutasi memeriksa CSRF; login/rate limiter bukan proteksi bot skala
distribusi. Rate limiter in-process, bukan cluster-wide service.

Header CSP/no-store/nosniff dan rendering React membatasi exposure. Tidak menyimpan
credential/DEK/data anggota di localStorage/sessionStorage/IndexedDB sebagai
arsitektur layanan. Test memeriksa raw JSON/network/storage, bukan sekadar elemen
yang terlihat. Respons yang sah mengandung plaintext sesuai hak tetap bisa dibaca
penerima sah/mesin yang dikuasai; “tidak tersimpan” bukan anti-screen capture.

Audit mencatat aktor/role/action/decision/id/class/request id/waktu, tanpa nilai
field, request body, token atau plaintext crypto. Error crypto/DB/validasi generik.
Audit bukan log immutable yang tahan OS/DB admin. Scope S06 seluruh log/history
masih perlu dibedakan dari bukti beberapa keluaran yang dipindai.

## A5 small-cell suppression di SQL

analyst_user ditolak SELECT anggota_protected dan analyst_view per record,
termasuk grant kolom. Interface public.analyst_summary milik schema_owner NOLOGIN,
security_barrier=true, owner-rights. Kolom dimension(text), value(text nullable),
anggota_count(bigint). Lima GROUP BY satu dimensi + HAVING count(*)>=5 + UNION ALL.
NULL membentuk kelompok dan ambang sama. Fungsi analyst_age_summary() membaca
hanya marginal age_band yang telah dirilis dengan SECURITY INVOKER.

Endpoint B membaca view ini lewat analyst_user dan memetakan count. total=null;
tidak menjumlahkan seluruh dimensi, tidak merilis label dengan count “<5”. Filter
dimension/value hanya memilih marginal yang sudah rilis; filter cohort anggota
lama ditolak422. Test sengaja membuat kelompok1–4 yang hilang dan >=5 benar.
Ini berbeda dari k-anonymity kombinasi REF pada dump dan tidak memberi DP.

## Perbedaan masking yang perlu diungkap

Toolkit A mempunyai fungsi masking yang mengikuti contoh panitia: nama dua huruf
per kata, NIK4depan+4belakang, telepon4+4, email2 huruf+domain, rekening4akhir.
**Runtime B tidak memakai seluruh fungsi itu**. `app/backend/service_app/policy.py`
memakai nama2 huruf+***, email1 huruf+***@***, identifier lain delapan bintang+2akhir,
dan nilai panjang<=4 menjadi****. Mask runtime lebih menyembunyikan beberapa bagian,
tetapi tidak sama formatnya dengan contoh panitia.

Nama detail operator memang dibuka menurut field policy; rekening finance dibuka
sesuai hak, bukan dimasking untuk semua role. Jangan menulis “semua tampilan
memakai format masking toolkit/panitia” atau “finance hanya melihat4 digit” tanpa
penyesuaian kode dan retest. Ini gap kesesuaian format/penjelasan, bukan bukti bahwa
raw ciphertext/token/field terlarang sudah diterima browser. Pengguna belum meminta
perubahan aplikasi pada tugas laporan ini.

## Bukti lab, web deployment dan operator VM — jangan dicampur

Origin demo yang diberikan pengguna dan dicatat pada evidence adalah
`https://43.156.157.247`. Penyusunan konteks ini tidak melakukan health check,
login, pentest atau inspeksi SSH baru pada origin tersebut.

1. **Lab A+B setelah A5**:143 checks,17 record buatan sendiri, PG 18/OpenBao TLS nyata,
   backup/restore tujuh tabel, HTTPS API/Next dan Chrome nyata, CA/hostname negative,
   tamper/retention/scope/field/raw/browser. Native binary fallback karena Docker
   host timeout. Chrome memakai pin SPKI fixture tepat, bukan bypass TLS global.
2. **Deployment web Alby**:100 checks pada enam akun existing, HTTPS trust normal,
   data anggota read-only. Login/logout menulis metadata sesi/audit. Tidak SSH,
   tidak memeriksa SQL/internal TLS/commit seluruh VM langsung.
3. **Bukti operator B lebih baru**: VM Ubuntu protected_734 berisi734, enam role demo,
   delapan akun pentest, A5 SQL checks, pembuatan golden dan **satu reset guarded
   nyata**,65 smoke checks. Provenance laporan: operator memakai SSH terautentikasi
   dan mengunduh metadata. Ini memperluas bukti tertentu, bukan pentest whitebox
   lengkap, bukan klaim Alby melakukan SSH, bukan semua recovery key-plane diuji.

Bukti B menyatakan belum memverifikasi cloud security groups, split key custody,
auto-renew certificate end-to-end, audit log aplikasi lengkap dan pentest penuh
Delf. Golden reset dapat mengganti DB demo dengan guard; gunakan saat maintenance
dan berizin, bukan perintah rutin setelah pull. Review hasil pentest yang nanti
masuk harus dicatat sebagai bukti baru, bukan digabung diam-diam dengan metadata ini.
