> **Pembaruan 28 Oktober 2026:** bagian lama di bawah dipertahankan sebagai riwayat.
> Pemulihan layanan A+B: [backup tujuh tabel dan cutover restore](docs/RECOVERY.md).
> Toolkit/schema/test vectors A kini tersedia dan integrasi protected disposable telah diuji.
> Gunakan Python **3.11+ (diuji 3.12.10)** dan `dprcrypto:public-v1`.
> Panduan terbaru yang menggantikan asumsi factory, akun/audit dan principal lama:
> [Integrasi A/B](docs/INTEGRATION_A.md), [adapter aktual](docs/CRYPTO_ADAPTER.md).
> `app.principal` protected adalah **UUID akun**, bukan hex blind index.
> Target yang didukung juga mencakup `baseline_1m` dan `protected_1m`;
> dataset 1M/migrated protected lokal belum diuji. Tidak ada regenerasi baseline_1m.

# Modul B — Service Application dan Access Control

Pemilik: Zhafif, branch `feat/service-app`. Aplikasi ini mempertahankan Python/FastAPI dan Next.js/TypeScript dari aplikasi sebelumnya, dengan kode Modul B seluruhnya di `app/`. Folder `apps/` lama, scanner, infra, toolkit, migrasi dan benchmark A/C tidak diubah.

Satu kode menyediakan `MODE=plain` untuk `baseline_100k` dan `MODE=protected` untuk `protected_100k`/`protected_734`. Endpoint, role, bentuk DTO dan pagination sama. Protected tidak pernah beralih ke plain ketika toolkit, key, TLS atau dekripsi gagal. [Matriks akses](ACCESS_MATRIX.md), [catatan keputusan/batas](NOTES.md), dan [interface crypto A](docs/CRYPTO_ADAPTER.md) adalah bagian dari handoff.

**Status target tim:** periksa `app/evidence/access-control/` dan `python app/scripts/check_ready.py`. Lab lokal Zhafif kini menyediakan `pg-dpr`, TLS dan `baseline_100k` dari datagen C seed 42; panduan reproduksi ada di [LOCAL_LAB.md](docs/LOCAL_LAB.md). Toolkit `toolkit/dprcrypto`, protection profile dan test vectors Modul A masih belum tersedia. Bukti plain lokal 100k, probe disposable dan driver crypto tiruan memiliki cakupan berbeda; tidak membuktikan protected/live OpenBao atau benchmark resmi.

## Prasyarat dan instalasi PowerShell

Jalankan perintah dari **root repository `juara1onno`**, bukan dari `app/backend`. Python 3.10+ untuk backend, Node.js 24 LTS untuk frontend; ikuti versi yang disepakati Modul A bila toolkit memerlukan versi Python lebih baru. PostgreSQL runtime harus versi 18 sesuai kontrak dan sudah dilengkapi TLS. Docker Desktop hanya diperlukan untuk probe disposable di bawah.

```powershell
python -m venv app/.venv
app/.venv/Scripts/python -m pip install -r app/requirements.txt
Push-Location app/web
npm ci
npm run build
Pop-Location
```

File `.env.example` hanya mendokumentasikan nama variabel. Backend sengaja tidak membaca `.env` lab lama di root; injeksikan konfigurasi ke environment proses. Jangan memasukkan password/token ke argumen command, source, history, screenshot atau chat. Jangan memakai URL koneksi DBA sebagai `DATABASE_URL` aplikasi.

## Siapkan database target bersama Modul A/C

1. C menyediakan `baseline_100k.public.anggota`; A menyediakan schema protected, role dan RLS sesuai kontrak. `postgres` sumber 734 baris tidak boleh menjadi target aplikasi/setup.
2. A menyediakan role `app_user`, `analyst_user`, `auditor_user`, sertifikat/CA PostgreSQL dan hak setup terbatas. Runtime harus `NOSUPERUSER`, `NOBYPASSRLS`, tanpa DDL. Analytics menggunakan `analyst_view`, auditor hanya `audit_log`.
3. Dengan persetujuan DBA A/C, setup B hanya membuat tabel kontrol `users`, `sessions`, `audit_log` dan grant minimum. Skrip tidak membuat/drop tabel anggota atau mengubah baris dataset. Penggunaan baseline untuk benchmark tulis harus dikoordinasikan dengan C, memakai snapshot/reset sebelum setiap run.

```powershell
# Isi APP_SETUP_DATABASE_URL lewat secret injection atau prompt aman;
# targetnya harus database yang dipilih dan sslmode=verify-full + sslrootcert.
app/.venv/Scripts/python app/scripts/schema.py --database baseline_100k
```

`schema.py` tidak membuat role PostgreSQL, mengubah PK/format crypto, membuat policy protected, mengaktifkan TLS server, atau menjalankan migrasi A. Kekurangan hak/role harus dibereskan oleh pemilik modul, bukan diatasi dengan menjalankan service sebagai superuser.

Contoh helper PowerShell berikut meminta password secara tersembunyi. Ubah host/port hanya ke PostgreSQL lab yang diotorisasi; contoh kontrak tim memakai `127.0.0.1:5433`. CA harus tersedia dari A. Jangan menyalin private key atau CA signing key ke Git.

```powershell
$env:MODE = 'plain'
$env:APP_ORIGIN = 'https://localhost:3443'
$env:SESSION_TTL_SECONDS = '900'
$pgCaFile = Read-Host 'Path absolut root CA PostgreSQL dari Modul A'
function Set-ServiceDbUrl([string]$variable, [string]$role, [string]$database) {
    $securePassword = Read-Host "Password role $role" -AsSecureString
    $credential = [pscredential]::new($role, $securePassword)
    try {
        $escapedPassword = [uri]::EscapeDataString($credential.GetNetworkCredential().Password)
        $escapedCa = [uri]::EscapeDataString($pgCaFile)
        $value = "postgresql+psycopg://${role}:${escapedPassword}@127.0.0.1:5433/${database}?sslmode=verify-full&sslrootcert=${escapedCa}"
        [Environment]::SetEnvironmentVariable($variable, $value, 'Process')
    } finally {
        Remove-Variable credential,securePassword,escapedPassword,value -ErrorAction SilentlyContinue
    }
}
Set-ServiceDbUrl 'DATABASE_URL' 'app_user' 'baseline_100k'
Set-ServiceDbUrl 'ANALYST_DATABASE_URL' 'analyst_user' 'baseline_100k'
Set-ServiceDbUrl 'AUDITOR_DATABASE_URL' 'auditor_user' 'baseline_100k'
# AUTH_DATABASE_URL optional; default memakai DATABASE_URL.
```

`sslmode=verify-full` dan CA file wajib di runtime, termasuk MODE=plain. Tidak ada fallback `sslmode=disable/prefer` atau `verify=False`. Nilai `DATABASE_URL` dan environment secret tidak dicetak oleh launcher.

## Akun demo dan principal anggota

Siapkan `DPR_PRIVATE_DIR` sebagai direktori khusus di luar checkout dengan ACL terbatas. `DEMO_MEMBER_PRINCIPAL` adalah nilai `pengguna` sintetis yang diotorisasi dari dataset target; baca lewat input tersembunyi/secret store. Jangan mengambil atau mengubah database `postgres` untuk provisioning.

```powershell
$env:DPR_PRIVATE_DIR = Join-Path $env:LOCALAPPDATA 'DPR/service-b-private'
$principalSecret = Read-Host 'Pengguna sintetis untuk akun anggota' -AsSecureString
$principalCredential = [pscredential]::new('principal', $principalSecret)
try {
    $env:DEMO_MEMBER_PRINCIPAL = $principalCredential.GetNetworkCredential().Password
    app/.venv/Scripts/python app/scripts/provision.py
} finally {
    Remove-Variable principalSecret,principalCredential -ErrorAction SilentlyContinue
    Remove-Item Env:DEMO_MEMBER_PRINCIPAL -ErrorAction SilentlyContinue
}
```

Enam akun dibuat dengan password acak Argon2id; password hanya ditulis di child directory privat `$env:DPR_PRIVATE_DIR/service-b/` ke file `service-b-plain-accounts.json` atau `service-b-protected-accounts.json`, bukan terminal. Child directory dibatasi memakai utility ACL Windows Modul A; parent private directory tidak diubah. Provisioning menolak menimpa akun/file yang sudah ada. Akun `anggota` dicocokkan melalui principal `pengguna` pada plain. Pada protected, provisioning hanya menyimpan blind index `pengguna_bidx` sebagai binding akun, tanpa salinan identifier plaintext. Password akun demo bukan password database dan tidak di-hardcode.

## Jalankan backend dan frontend dengan HTTPS

Backend menggunakan sertifikat lokal Modul A. Server API dan frontend memerlukan cert/key server; CA signing private key tidak diperlukan. Browser perlu mempercayai CA lokal A. `OPENBAO_CACERT`, CA PostgreSQL dan CA browser dapat berbeda; jangan menganggap satu jalur TLS membuktikan seluruhnya.

Terminal backend, setelah environment runtime di atas disiapkan:

```powershell
$env:TLS_CERT_FILE = Join-Path $env:DPR_SECRETS_DIR 'tls/server.crt'
$env:TLS_KEY_FILE = Join-Path $env:DPR_SECRETS_DIR 'tls/server.key'
$env:API_PORT = '8100'
app/.venv/Scripts/python app/scripts/serve.py
```

Terminal frontend, isi TLS file dan CA yang sama dari material server A sebelum memulai Node:

```powershell
$env:TLS_CERT_FILE = Join-Path $env:DPR_SECRETS_DIR 'tls/server.crt'
$env:TLS_KEY_FILE = Join-Path $env:DPR_SECRETS_DIR 'tls/server.key'
$env:NODE_EXTRA_CA_CERTS = Join-Path $env:DPR_SECRETS_DIR 'tls/ca.crt'
$env:API_INTERNAL_URL = 'https://127.0.0.1:8100'
$env:WEB_PORT = '3443'
Push-Location app/web
npm start
Pop-Location
```

Buka **https://localhost:3443/login**. UI melakukan semua request API melalui `/api` pada origin yang sama. Kedua launcher menolak start tanpa cert/key; tidak fallback HTTP. Proxy backend memverifikasi CA melalui trust Node, bukan `NODE_TLS_REJECT_UNAUTHORIZED=0`. Session HttpOnly/Secure/SameSite Strict berumur pendek; CSRF diwajibkan untuk mutasi. CSP menggunakan nonce per request, tanpa `unsafe-inline`/`unsafe-eval`; halaman personal tidak dicache dan data/token tidak disimpan di localStorage/sessionStorage.

## MODE=protected dan handoff crypto

Pakai environment/kredensial workload OpenBao `svc-app` dari A, bukan root token. Instal atau letakkan paket A di `toolkit/dprcrypto`, lalu jalankan launcher yang sama:

```powershell
$env:MODE = 'protected'
# DATABASE_URL, AUTH_DATABASE_URL, ANALYST_DATABASE_URL, AUDITOR_DATABASE_URL
# harus menunjuk protected_100k atau protected_734 dengan role dan TLS yang sama.
$env:OPENBAO_ADDR = 'https://127.0.0.1:8200'
$env:OPENBAO_CACERT = Join-Path $env:DPR_SECRETS_DIR 'tls/ca.crt'
$env:DPR_CRYPTO_FACTORY = 'dprcrypto:create_service'
# OPENBAO_TOKEN diinjeksikan dari secret store/material workload A tanpa dicetak.
app/.venv/Scripts/python app/scripts/serve.py
```

Adapter B hanya menjembatani [lima operasi toolkit A](docs/CRYPTO_ADAPTER.md), meminimalkan kolom/DEK yang diminta, dan menerjemahkan exception menjadi HTTP 500 generik dengan audit metadata. Tidak ada AES/HMAC/unwrap implementasi baru di Modul B. Tidak adanya factory, CA/token, schema, test vector atau format yang cocok menghasilkan kegagalan tertutup; jangan menjalankan protected dengan crypto test double.

## Endpoint final dan pembatasan

| Endpoint | Perilaku |
|---|---|
| `GET /auth/csrf`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | Session cookie, CSRF, limiter login, expiration/revocation |
| `GET /anggota?page=1` | 50 per halaman; hanya locator dan nama, masking per peran |
| `GET /anggota/{anggota_id}` | DTO eksplisit per peran, object scope sebelum query/dekripsi |
| `GET /anggota/search?no_ktp=...` atau `?email=...` | Exact lookup; protected melalui blind index toolkit A |
| `PATCH /anggota/{anggota_id}/kontak` | Hanya `email`/`handphone`, field baru divalidasi, re-encrypt/update email bidx atomik |
| `POST /anggota` | Insert privileged_officer untuk workload tulis, 29 field sumber tervalidasi |
| `GET /analytics/summary` | Analyst saja, agregat lewat koneksi `analyst_user`/`analyst_view` |
| `GET /audit?page=1` | Auditor saja, metadata melalui koneksi `auditor_user` |

Locator API berupa string legacy yang stabil di kedua mode; UUID internal protected tetap UUIDv4 acak dan digunakan untuk AAD. ID bukan izin akses. Peran anggota tidak bisa membaca/memperbarui ID orang lain. Nama/KTP/kontak yang termasking sudah dimasking di backend, bukan sekadar CSS. Query hanya memuat kolom yang diperlukan; protected batch unwrap per halaman dan tidak meminta DEK FIN tanpa izin FIN. Lihat matriks untuk field persisnya.

Pencarian GET mengikuti PROMPT_B. Karena URL internal membawa NIK/email, access log API dimatikan dan proxy tidak mencetak URL/body upstream saat error. Jangan mengaktifkan query logging atau reverse-proxy access log yang menyimpan query string sensitif.

## Pengujian dan evidence

Tes cepat memakai SQLite sementara dan fixture sintetis buatan sendiri. Mode parity protected dengan fake driver hanya menguji policy/DTO/wiring, bukan algoritma/interoperabilitas OpenBao. Raw output tes tetap lokal; ringkasan mesin disanitasi.

```powershell
New-Item -ItemType Directory -Force app/.local | Out-Null
app/.venv/Scripts/python -m pytest -c app/pytest.ini --basetemp app/.local/testtmp app/tests -q --junitxml=app/.local/security-tests.xml
app/.venv/Scripts/python app/tests/export_results.py
Push-Location app/web
npm run build
npm run test:ui
Pop-Location
```

`test:ui` selalu menulis ringkasan mesin baru, termasuk ketika browser/runner gagal; hasil PASS lama tidak dipakai ulang. Report frontend disalin otomatis ke `app/evidence/access-control/browser-tests.json`, tanpa body respons atau credential.

Probe nyata yang tidak memerlukan database tim atau credential statis:

```powershell
# CA generator A dipakai sebagai library; tidak ditulis ulang di B.
app/.venv/Scripts/python -m pip install -r infra/requirements.txt
Push-Location app/web
npx playwright install chromium
Pop-Location
app/.venv/Scripts/python app/scripts/integration_probe.py
app/.venv/Scripts/python app/scripts/check_ready.py
```

Probe membuat project Docker acak, PostgreSQL 18 dengan sertifikat temporer dari generator A di luar checkout, database baru `dpr_b_test_*`, role minimum, forced RLS fixture dan data uji buatan sendiri. Ia menguji TLS `verify-full`, penolakan CA salah, SQL principal transaction reset, matriks API dan alur browser HTTPS nyata melalui Next→FastAPI→PostgreSQL. Browser menggunakan pin SPKI khusus sertifikat uji; tidak menonaktifkan verifikasi TLS secara global. Semua password tiba di proses browser hanya melalui stdin. Proses dan volume acak milik probe dibersihkan; instance/database tim dan aplikasi lain tidak dihentikan.

Default evidence berada di **`app/evidence/access-control/`** untuk mematuhi batas perubahan hanya `app/`. Jangan menyalin raw JUnit/trace, body respons, cookie, key atau credential ke evidence bersama. Tim dapat mengekspor ringkasan ke `evidence/access-control/` saat integrasi main. Kelulusan probe disposable tidak menggantikan integrasi `baseline_100k`, live toolkit/test vectors A, role/RLS target atau benchmark API C.

Benchmark resmi tetap milik C: transport/auth/DTO sama untuk plain/protected, 50 record per halaman, workload/seed/record mapping sama, dan reset fixture tulis antar-run. Re-login sebelum run bila session akan kedaluwarsa; jangan menambah auth bypass atau menonaktifkan audit/CSRF demi angka. Jangan menjalankan browser mutasi bersamaan dengan benchmark.

Setelah selesai, tutup proses Node/Python milik terminal dan hapus environment secret dari sesi. Data/kunci privat tetap mengikuti custody dan retensi yang disepakati A/C. Daftar keterbatasan terbaru berada di `NOTES.md`; tidak ada klaim production-ready atau kelulusan kontrak protected dari mock test.

## Instalasi dan verifikasi setelah integrasi main b8e9998

Gunakan venv Python 3.11+; jangan memakai venv lama Python 3.10 untuk toolkit A.
Perintah berikut dijalankan dari root repo, dengan Docker Desktop aktif untuk probe.

```powershell
py -3.12 -m venv app/.venv
app/.venv/Scripts/python -m pip install -r app/requirements.txt -r infra/requirements.txt -e ./toolkit
Push-Location app/web
npm ci
npm run build
npx playwright install chromium
npm run test:ui
Pop-Location
app/.venv/Scripts/python -m pytest -c app/pytest.ini --basetemp app/.local/testtmp app/tests -q --junitxml=app/.local/security-tests.xml
app/.venv/Scripts/python app/tests/export_results.py
app/.venv/Scripts/python -m dprcrypto.vectors verify --evidence app/evidence/access-control/crypto-vectors.json
app/.venv/Scripts/python app/scripts/protected_probe.py
app/.venv/Scripts/python app/scripts/check_ready.py
```

Untuk lab plain existing, gunakan `app/.venv/Scripts/python app/scripts/local_lab.py verify`.
Tidak perlu menjalankan setup/datagen ulang. Hindari benchmark bersamaan dengan probe mutasi.
Protected memakai `app_users`, `access_scope`, `audit_log` milik A; setup B hanya menambah
`service_sessions`, `service_member_bindings`, dan sequence locator. Provisioning protected
memerlukan kredensial setup terpisah dan `DEMO_ASSIGNED_IDS` eksplisit, sesuai panduan integrasi.

Analytics mendukung filter equality `jenis_kelamin`, `pekerjaan_terakhir`, `nama_kppn`,
`nama_bank`, `age_band`. Jumlah 1–4 dikirim sebagai string `"<5"`, bukan angka mentah;
jumlah sekunder/total yang perlu disembunyikan menjadi `null`. UI menampilkan null sebagai
“Disembunyikan”. Konsumen DTO harus menerima `number | "<5" | null`; kunci respons tetap
`total` dan `groups`. Pengujian filter, batas 4/5 dan rendering tercakup di evidence.


## Revisi analytics A5/B4 — 28 Oktober 2026

Bagian ini menggantikan petunjuk analytics/filter/suppression lama di atas.
Sesuai CONTRACT 10.1, endpoint kini membaca `public.analyst_summary` sebagai
`analyst_user`. Response tetap `{total, groups}`: total selalu null dan groups hanya
berisi dimension/value/count dengan count integer >=5. Kelompok 1–4 beserta labelnya
hilang seluruhnya; tidak dikirim sebagai `<5`, null-count, atau label kosong.
Filter yang tersedia hanya `dimension` dan `value` untuk marginal yang sudah dirilis;
value memerlukan dimension. Semua filter cohort anggota lama ditolak 422.

SQL A5 dan aplikasi harus dirilis bersama. Lihat [panduan VM](docs/DEPLOY_A5.md).
Jangan menjalankan full migration prepare, provisioning akun, atau mengubah pg-dpr
selama benchmark. Kode saja tidak menerapkan perubahan SQL. Fixture unit adalah
sintetis SQLite; pengujian UI memakai API mock. Keduanya tidak menyatakan A5 VM PASS.
Evidence khusus: `app/evidence/access-control/analytics-a5.json`.

## Kit pentest VM Zhafif

Panduan [PENTEST_SETUP.md](docs/PENTEST_SETUP.md) menyediakan provisioning8 akun
`pt.*` terpisah, login6 demo existing, systemd dua proses aplikasi, inventory metadata,
template golden dan reset cadangan yang dibatasi ke protected_734.
[Brief Delf](../docs/deploy/PENTEST_BRIEF.md) berisi D1–D12 dan peta scope tanpa password.
File credential tetap di private server mode600, bukan repo. Restore utama tetap
tooling Alby; golden tidak menggantikan backup atau key plane OpenBao.
Pengujian lokal memakai fixture/fake katalog dan dipisahkan dari bukti live.
**Reset VM PASSED** satu kali; laporan aktual tersimpan di
`app/evidence/access-control/vm-golden-reset.json`: members734 dan14 akun lulus.
Inventory/A5/provision/golden berasal dari VM nyata; SG provider tetap belum diverifikasi.

## Clone benchmark API

`DPR_BENCHMARK_DATABASE` memilih satu clone `api_*` secara eksplisit pada MODE plain
atau protected. Seluruh URL runtime tetap role minimal dan verify-full pada target
yang sama. CLI schema/provision mendukung clone, setup memberi CONNECT/USAGE terbatas
dan runtime memeriksa metadata/marker/schema/RLS sebelum melayani request.
Lihat [handoff benchmark untuk Delf](docs/BENCHMARK_CLONES.md). Default database demo
tetap sama. Fitur ini tidak menjalankan benchmark atau mengubah runner/cleanup C.

## Perbaikan F-01 — 29 Oktober 2026

POST anggota menolak KTP non-NULL yang sudah terdaftar dengan409 generik. Normalisasi
format mempertahankan nol awal dan identitas sintetis14digit. Protected wajib
menerapkan sql/protected/04_identity_unique.sql sesudah reset golden resmi. Detail
migrasi, pengujian race/RLS dan pemulihan: [F01_DUPLICATE_IDENTITY.md](docs/F01_DUPLICATE_IDENTITY.md).

## Token aplikasi otomatis

Paket operator satu kali memasang AppRole svc-app dan timer lima menit. Token tetap
berumur maksimal empat jam; token baru dipasang sebelum sisa TTL satu jam, lalu hanya
API dimuat ulang. Tidak memakai root token dalam tugas rutin, tidak mengubah akun/data,
dan tidak restart database/OpenBao. Ada jeda singkat saat API restart. Cara pasang,
lokasi credential privat, status, batasan, dan pencabutan:
[TOKEN_AUTOREFRESH.md](docs/TOKEN_AUTOREFRESH.md).
