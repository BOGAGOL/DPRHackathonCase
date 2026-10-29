> **Pembaca baru/juri:** mulai dari [panduan reproduksi lengkap](../../docs/operations/REPRODUCTION.md).
> Dokumen ini adalah runbook modul/lingkungan tertentu; jangan menerapkannya ke server existing tanpa memilih prosedur yang sesuai.

# Acceptance sistem gabungan setelah A5

Pekerjaan ini membedakan dua bukti: lab terisolasi dengan semua service nyata dan
pengujian deployment yang hanya memakai antarmuka web. Tidak menjalankan benchmark,
tidak mengubah dataset benchmark/sumber, dan tidak melakukan backup/restore pada VM.

## Lab nyata setelah restore

Prasyarat: virtualenv dependensi A+B, Node, Chrome terpasang, dependensi frontend
sesuai `app/web/package-lock.json`, binary PostgreSQL 18 dan OpenBao 2.5.5 resmi.
Pada sesi ini Docker Desktop timeout; lab memakai binary native PG18.6 dan Bao2.5.5.
Archive Bao diverifikasi terhadap `checksums-windows.txt` dari release resmi
https://github.com/openbao/openbao/releases/tag/v2.5.5 sebelum dieksekusi.

```powershell
# Jalankan dari root repo. Path tool di bawah adalah contoh instalasi lokal sesi ini.
$env:DPR_POST_A5_ACCEPTANCE = '1'
$env:DPR_NATIVE_PG_BIN = Join-Path $env:LOCALAPPDATA 'DPR\test-tools\pg18\pgsql\bin'
$env:DPR_NATIVE_BAO_BIN = Join-Path $env:LOCALAPPDATA 'DPR\test-tools\bao-2.5.5\bao.exe'
Push-Location app/web
npm ci --no-fund --no-audit
npm run build
Pop-Location
.venv/Scripts/python -m pytest scripts/backup/tests/test_post_a5_acceptance.py infra/tests/test_acceptance_helpers.py -q --tb=short
```

Test membuat cluster baru pada port loopback acak, password SCRAM acak, TLS wajib,
CA lokal khusus fixture, dan OpenBao server biasa dengan storage file. Tidak memakai
dev mode OpenBao, HTTP, SQLite, FakeCrypto, respons API mock, atau pg-dpr existing.
Init/unseal otomatis hanya pada OpenBao **baru milik fixture**, tanpa material existing.
Semua kunci/token/password tetap pada memori atau folder privat fixture di luar Git;
DEK hanya di memori, pg_dump langsung dialirkan ke enkripsi backup. Proses milik
fixture dihentikan saat selesai. Tidak memasang Windows service atau sertifikat CA global.

Transport `psql`/`pg_dump`/`pg_restore` diganti dari `docker exec` menjadi binary PG18
lokal; builder SQL provisioning, crypto/toolkit, RLS/ACL, aplikasi, enkripsi/HMAC backup,
validasi dan proses restore adalah implementasi proyek yang sama. Lab berisi 17 record
buatan sendiri: satu label pekerjaan singleton dan 16 anggota pada kelompok yang dirilis.
Update dan insert hanya terjadi pada clone hasil restore milik test.

Alur: A schema + SQL A5 -> enkripsi lewat Transit -> kontrol B/enam akun -> backup
tujuh tabel -> restore tanpa OpenBao (tetap ciphertext) -> restore dengan OpenBao ->
HTTPS backend -> Next HTTPS -> Chrome nyata. Browser memeriksa raw JSON, cookie,
storage, akses role/record/field, agregat, filter terlarang dan logout. SQL analis
langsung ditolak untuk raw table/view (42501). CA/hostname PostgreSQL salah ditolak.
Backup tamper dan retention drill juga dijalankan pada clone terpisah.

Chrome lokal mempercayai tepat SPKI sertifikat fixture pada localhost; klien HTTPS
lain memakai CA fixture dengan verifikasi hostname. `ignoreHTTPSErrors` tetap false,
tidak ada flag bypass TLS global atau perubahan trust store Windows. Runtime web
tidak mewarisi credential DB/admin/OpenBao; runtime API mendapat hanya tiga URL
role layanan dan token svc-app.

Hasil: `evidence/backup/service-recovery-integration.json`. Ringkasan penerimaan
dan scope final: `evidence/acceptance/post-a5-summary.json`.

## Deployment VM

Target sesi: `https://43.156.157.247`. `browser.mjs` juga dipakai dengan enam akun
existing, Chrome nyata, trust HTTPS bawaan, tanpa SPKI lokal atau bypass sertifikat.
Input JSON hanya melalui stdin: `{baseURL, accounts:{<role>:{username,password}}}`.
Contoh berikut membaca **file privat di luar repo**, tanpa mencetak akun/password:

```powershell
$env:DPR_DEPLOYMENT_CREDS_FILE = Join-Path $env:LOCALAPPDATA 'DPR\acceptance-private\deployment-credentials.json'
@'
import json,os,subprocess
from pathlib import Path
from datetime import datetime,timezone
accounts=json.loads(Path(os.environ['DPR_DEPLOYMENT_CREDS_FILE']).read_text())
config={'baseURL':'https://43.156.157.247','accounts':{
    a['role']:{'username':a['username'],'password':a['password']} for a in accounts}}
r=subprocess.run(['node','infra/acceptance/browser.mjs'],input=json.dumps(config),
    capture_output=True,text=True,timeout=240)
report=json.loads(r.stdout)
report.update(checked_at_utc=datetime.now(timezone.utc).isoformat(),
    scope='deployed VM; real Chrome/HTTPS; six existing accounts; member data read only',
    origin=config['baseURL'],server_database_or_key_configuration_changed=False)
serialized=json.dumps(report,indent=2)
assert all(a['password'] not in serialized for a in accounts)
out=Path('evidence/acceptance/deployed-browser.json');out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(serialized+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'checks':len(report['checks'])}))
'@ | .venv/Scripts/python -
```

File input berupa list enam objek `username/password/role`. Jangan commit file ini.
Sesi awal menerima `creds.json` dengan pembungkus teks; objek JSON diekstrak tanpa
mengeksekusi pembungkus dan disalin ke folder privat. Nama `creds.json` dikecualikan
melalui `.git/info/exclude` lokal; tidak menjadi artefak/evidence Git.

Pengujian VM membaca data melalui akun berizin serta membuat/mencabut sesi dan
metadata audit login normal. Tidak PATCH/INSERT anggota, provisioning, perubahan
password/role, akses SSH, perubahan OpenBao, atau restore VM. Tidak merekam screenshot,
trace, cookie, respons berisi data anggota, atau isi log. Bukti VM tidak mengesahkan
ACL/TLS backend-DB/OpenBao secara langsung atau commit server; verifikasi internal
VM memerlukan hasil `infra.protected.analyst --verify-only`, verifier A dan akses
operator tersendiri. Bukti internal lengkap pada sesi ini berasal dari lab nyata.

## Batas klaim

- Lab sintetis 17 record tidak menggantikan penerimaan dataset tim 734/100k/1m,
  pengujian kapasitas, benchmark resmi, atau DR seluruh server/key-plane.
- Browser deployment lulus tidak membuktikan build VM sama dengan HEAD lokal.
- Tidak menyimpulkan tidak ada kebocoran di seluruh log/riwayat host. Scope evidence
  hanya cek yang disebut, tanpa plaintext/kredensial pada output pengujian.
- Percobaan awal helper import dan penemuan Chrome native yang gagal disimpan di
  `evidence/acceptance/history/`; hasil final tidak menghapus riwayat kendala tersebut.
