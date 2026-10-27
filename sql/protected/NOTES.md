# Tahap 3: skema dan integrasi Service App

Skema mengikuti kontrak: 25 kolom bytea `_ct`, 3 bidx bytea 32 byte, dua wrapped
DEK, UUIDv4, legacy ID unik, protection_version=1, 4 REF dan age_band.
Constraint memeriksa bentuk blob v1, bukan keaslian tag; autentikasi kriptografis
tetap dilakukan `dprcrypto`. NULL sumber tetap diperbolehkan pada field data.
`analyst_view` hanya mengeluarkan jenis_kelamin, pekerjaan_terakhir, nama_kppn,
nama_bank, age_band. Tidak ada UUID/legacy ID, ciphertext, bidx, atau wrapped DEK.

`schema_owner` NOLOGIN memiliki semua objek. View memakai security barrier dan
hak owner; owner memiliki policy SELECT agar view aman tetap bekerja saat
FORCE ROW LEVEL SECURITY aktif. Login analis tidak menjadi anggota owner dan
tidak dapat membaca tabel dasar. Fungsi agregat hanya membaca view tersebut.

## Penerapan pada pg-dpr lokal

Jalankan dari root repo setelah PostgreSQL 18/TLS dan kedua DB target tersedia:

```powershell
.\.venv\Scripts\python.exe -m pip install -r infra/requirements.txt
$env:DPR_SECRETS_DIR = Join-Path $env:LOCALAPPDATA 'DPR\crypto-infra-tls'
.\.venv\Scripts\python.exe -m policy.build_profile
.\.venv\Scripts\python.exe -m infra.protected.apply --database protected_734 --create-local-credentials
.\.venv\Scripts\python.exe -m infra.protected.apply --database protected_100k --create-local-credentials
```

Wrapper menjalankan bootstrap role -> skema -> GRANT dalam **satu transaksi**,
memeriksa PG18/nama target/owner objek/profile, dan mencocokkan identitas cluster
koneksi TLS port5433 dengan container. SQL melalui socket lokal container;
inspeksi akhir melalui TLS verify-full. Tidak ada recreate container, perubahan
skema pada source `postgres` atau `baseline_100k`, maupun migrasi baris.
Penerapan ulang mempertahankan baris dan password role; ketidakcocokan kolom
kriptografi/owner ditolak, bukan dihapus. Jangan menjalankan SQL ini pada database sumber.

Admin dapat disediakan lewat PGUSER/PGPASSWORD/PGHOST/PGSSLROOTCERT (port tetap
5433), atau credential DPAPI lokal yang sudah disiapkan tahap infra. Password
ketujuh login role berasal dari `DPR_<ROLE>_PASSWORD` (lihat NOTES role). Opsi
`--create-local-credentials` membuat password CSPRNG saat belum ada, menyimpan
hanya PSCredential DPAPI di luar repo `postgres/roles/<role>.credential.xml`.
DPAPI terikat akun/mesin Windows; env mengalahkan DPAPI. Password diberikan ke
psql lewat env, tidak lewat argv. Raw stdout/stderr provisioning tidak dicetak
karena ekspansi variabel psql dapat mengandung rahasia. Evidence metadata:
`evidence/schema/protected_734.json`, `protected_100k.json`.

## Handoff Modul B

Folder `app/` belum ada di checkout saat tahap ini dibuat. Tabel akun disediakan
di kedua DB protected; kode Service App belum diubah. Implementasi lama di
`apps/api/` memakai tabel/role lama dan perlu diadaptasi oleh pemilik Modul B.

- `app_users`: user_id UUID, username unik, password_hash Argon2id v19, role
  (`operator`, `privileged_officer`, `finance_officer`, `analyst`, `auditor`,
  `anggota`), active, timestamps. Tidak ada akun/password demo otomatis.
  CHECK hanya menolak format non-Argon2id; backend menentukan parameter biaya,
  memverifikasi password dan melakukan rehash bila diperlukan.
- Principal adalah `app_users.user_id` dari sesi yang telah diautentikasi,
  **bukan** parameter principal dari request. Login DB `app_user` mempunyai
  SELECT/INSERT/UPDATE akun sesuai kontrak; otorisasi pengelolaan akun/role wajib
  di backend. Jangan menyertakan hash password dalam DTO atau log.
- Set context **di dalam setiap transaksi**, termasuk transaksi baca. Contoh
  psycopg, query berparameter yang ekuivalen dengan SET LOCAL:

  ```python
  with connection.transaction():
      connection.execute("SELECT set_config('app.principal', %s, true)", (str(authenticated_user_id),))
      rows = connection.execute(
          "SELECT anggota_id, nama_ct FROM public.anggota_protected WHERE anggota_id = %s",
          (requested_anggota_id,),
      ).fetchall()
  ```

- `access_scope`: principal, anggota_id, permission `read`/`update`/`insert`,
  source_label `synthetic`/`manual`/`application`. Fixture uji berlabel synthetic;
  admin tepercaya memberi scope nyata. NULL anggota_id hanya untuk kapabilitas
  insert global. Tidak adanya principal/scope, principal invalid, atau akun
  nonaktif menolak akses. `update` juga mengizinkan SELECT record bersangkutan.
- `app_user` tidak boleh menulis scope atau DELETE anggota. Untuk insert,
  backend membuat UUIDv4 dan INSERT **tanpa RETURNING**; trigger AFTER INSERT
  memberi read+update hanya pada UUID baru kepada principal pemilik izin insert.
  SELECT berikutnya dalam transaksi yang sama bisa membaca UUID tersebut.
  RETURNING memerlukan policy SELECT sebelum trigger AFTER membentuk scope.
- `audit_log` berisi metadata tindakan, UUID, kelas field, keputusan, request_id;
  tidak ada payload nilai, token, atau DEK. Trigger merekam perubahan akun,
  anggota, scope; context actor/role/waktu/db login diisi server. App/migration
  hanya dapat append kolom event yang diizinkan, tidak UPDATE/DELETE log.
  Backend tetap harus mencatat read/decrypt, kegagalan otorisasi/dekripsi dan
  autentikasi; event pada transaksi rollback perlu transaksi audit tersendiri.
- Pencurian kredensial `app_user` memungkinkan penyerang mengubah
  `app.principal` dan memilih principal lain. **RLS ini defense-in-depth,
  bukan batas autentikasi yang independen dari Service App.** Uji integrasi
  sengaja menunjukkan spoof ini. Backend tetap wajib object/field authorization,
  pembatasan endpoint finance, masking, dan transaksi context per request.
  Superuser/owner juga merupakan pihak tepercaya; audit bukan immutable bagi DBA.

## Pengujian

```powershell
$env:DPR_SCHEMA_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m pytest policy/tests infra/tests/test_protected_provisioning.py infra/tests/test_protected_schema_integration.py -q
```

Test memakai container PG18 sementara, role/password acak, record sintetis;
tidak menghubungi database sumber. Evidence `evidence/schema/integration.json`
memuat hasil role, RLS, konteks transaksi, constraint, audit, dump/restore di memori,
idempotensi, serta penolakan role berbahaya/cluster yang berbeda. TLS dimatikan
hanya untuk fixture PostgreSQL disposable loopback; pg-dpr development tetap TLS.

Rujukan: [PostgreSQL 18 RLS](https://www.postgresql.org/docs/18/ddl-rowsecurity.html),
[CREATE VIEW](https://www.postgresql.org/docs/18/sql-createview.html).

## Hasil lokal 27 Oktober 2026

Penerapan ke protected_734 dan protected_100k pada pg-dpr berhasil. Empat tabel
di setiap DB masih kosong, tanpa akun demo atau fixture scope. Verifikasi TLS
dan checksum source postgres/734 serta baseline_100k/100000 tetap lulus;
lihat `evidence/development/verify.json`. Ini development lokal, bukan benchmark
resmi di laptop anggota tim lain.

Regresi `tests infra/tests toolkit/tests policy/tests` dengan flag integrasi
DPR_INFRA_INTEGRATION, DPR_CRYPTO_INTEGRATION, DPR_POSTGRES_TLS_INTEGRATION,
DPR_SCHEMA_INTEGRATION=1: **196 passed, 1 skipped**. Skip adalah fixture dataset
panitia pada suite historis yang tidak didistribusikan; validasi source lokal
734 terpisah tetap lulus. Ada satu warning deprecation dependensi Starlette pada
aplikasi lama. Evidence JUnit `evidence/schema/tests-stage3.xml`; seluruh
**61 pemeriksaan** integrasi skema/role/RLS/dump-restore berhasil.

Adaptasi rujukan Onno: baca `sql/20-protected-v2.sql`, `30-roles-grants.sh`,
`40-rls.sql` di paket reference. Pola bytea/indeks/HMAC, psql format %I/%L,
FORCE RLS dan current_setting dipertahankan konsepnya, dengan kolom sesuai
kontrak anggota, scope principal per record (bukan tenant), owner NOLOGIN,
password melalui getenv (bukan argumen CLI), serta allowlist role dan target.
