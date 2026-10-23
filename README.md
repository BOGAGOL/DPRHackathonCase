# DPR Secure Data Management System

Aplikasi layanan Next.js + FastAPI untuk melihat, mencari, dan memperbarui data anggota sesuai hak akses. Ini prototipe hackathon dengan dataset sintetis, bukan situs resmi DPR atau Privacy Scanner. Kode scanner/artefak Task 1 di luar checkout tidak diubah.

Sudah dijalankan pada Windows: PostgreSQL baseline/protected terpisah, import **734 × 29** tanpa perubahan nilai, autentikasi, role/record/field authorization, AES-256-GCM, blind lookup, edit kontak, audit, browser flows, backup/restore, dan benchmark tiga pengulangan termasuk **10.000 record sintetis baru**. Status dan evidence rinci ada di [PROGRESS.md](PROGRESS.md) dan [evidence/README.md](evidence/README.md). Docker Compose tervalidasi konfigurasinya; container runtime belum diuji karena Docker Engine tidak aktif. Live OpenBao dan TLS deployment: **NOT TESTED**.

## Jalankan lab lokal (Windows / PowerShell)

Prasyarat: Python 3.10+, Node.js 24 LTS, PostgreSQL 17 beserta `initdb`, `pg_ctl`, `pg_dump`, `pg_restore` di PATH. Port 3000, 8000, 55432, 55433 harus tersedia. Jalankan dari direktori README ini.

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r apps/api/requirements.txt
python scripts/configure.py
.venv/Scripts/python scripts/local_database.py start
.venv/Scripts/python scripts/bootstrap.py
.venv/Scripts/python scripts/manage.py import --source "../../Task1_Hackathon_DPR_2026/Task1_Hackathon_DPR_2026/anggota_dummy.sql"
.venv/Scripts/python scripts/manage.py provision
Push-Location apps/web
npm ci
npm run build
Pop-Location
./scripts/start-local.ps1
```

Buka **http://localhost:3000/login**. Empat username/password demo ada di **`.local/demo-accounts.json`**, dibuat acak saat provisioning dan diabaikan Git. Buka file tersebut secara privat; password tidak dicetak/ditulis pada source. Akun `viewer.demo`, `operator.demo`, `staff.demo`, `admin.demo` mempunyai izin berbeda. Tidak ada fallback login offline/mock.

Jika checkout ini sudah disiapkan, cukup jalankan `./scripts/start-local.ps1`. Jangan menjalankan `configure.py`/`provision` lagi untuk mengganti secret: keduanya menolak overwrite. Folder `.local/pg-*` adalah cluster baru proyek, tidak memakai atau mengubah cluster PostgreSQL yang sudah ada. `stop-local.ps1` menghentikan proses launcher dan kedua cluster lab proyek. Jangan menjalankan native lab dan Compose dengan port yang sama.

Untuk development di dua terminal: `.venv/Scripts/python scripts/serve.py`, lalu `cd apps/web; npm run dev`. API langsung tersedia di `http://127.0.0.1:8000`, OpenAPI development `/docs`. UI berkomunikasi melalui `/api` same-origin proxy; tidak membuka CORS. Jangan menampilkan cookie/credential pada screenshot demo.

## Jalur Docker Compose

Aktifkan Docker Desktop Linux Engine. Generate `.env` seperti di atas; dataset tetap di luar repository. Set `DATASET_PATH` di `.env` jika letaknya berbeda. Buat `.local` sebelum mounting.

```powershell
New-Item -ItemType Directory -Force .local
docker compose --profile lab up -d protected-db baseline-db
docker compose --profile lab --profile tools run --rm tools scripts/bootstrap.py
docker compose --profile lab --profile tools run --rm tools scripts/manage.py import --source /input/anggota_dummy.sql --evidence /workspace/.local/migration.json
docker compose --profile lab --profile tools run --rm tools scripts/manage.py provision
docker compose up --build -d api web
```

`api` memakai `app_user`, tanpa kredensial owner/baseline. `tools` adalah CLI terpisah untuk operasi privileged, source mount read-only, tidak ada route scanner/baseline. Baseline hanya aktif dengan profile lab dan network berbeda. Port DB hanya loopback. Compose ini development HTTP/local AES; pengaturan HTTPS/TLS/Transit dijelaskan dalam [runbook](docs/OPERATIONS.md). Jangan menggunakan `docker compose down -v` untuk menghentikan lab yang datanya perlu disimpan.

## Pengujian dan reproduksi evidence

```powershell
.venv/Scripts/python -m pytest -q --junitxml=evidence/security-tests.xml
.venv/Scripts/python scripts/manage.py verify --source "../../Task1_Hackathon_DPR_2026/Task1_Hackathon_DPR_2026/anggota_dummy.sql"
.venv/Scripts/python scripts/verify_security.py
.venv/Scripts/python scripts/backup.py drill
Push-Location apps/web
npx playwright install chromium
npm run test:e2e
Pop-Location
```

Python tests memakai DB SQLite sementara untuk policy/API/crypto; source dataset test benar-benar memverifikasi 734 record bila file tersedia. PostgreSQL/live API diverifikasi oleh tooling tersendiri. Tes browser membutuhkan layanan berjalan, dataset+akun terprovision, dan browser Chromium. Tidak ada trace/screenshot otomatis berisi data. Security tooling tidak boleh diarahkan ke sistem DPR sungguhan.

Benchmark dijalankan sendiri saat tidak ada mutasi browser/user:

```powershell
.venv/Scripts/python scripts/benchmark.py --operations 300 --repeats 3 --backup-restore
.venv/Scripts/python scripts/scale_lab.py --rows 10000
.venv/Scripts/python scripts/benchmark.py --env-file .local/scale.env --operations 300 --repeats 3 --backup-restore --output evidence/benchmark-scaled.json
```

Runner mengukur workload DB read/write 80/20, concurrency 1, output bisnis kontak yang setara, enkripsi/dekripsi, CPU/RAM runner dan native cluster, storage dan encrypted backup/restore. Ini **bukan benchmark HTTP/TLS**. Raw samples dan median disimpan dalam JSON; angka tidak boleh digeneralisasi ke kapasitas produksi. Scale generator membuat dua DB baru, tidak menambah record pada aplikasi demo. DB hasil restore dipertahankan untuk inspeksi.

## Struktur dan referensi

- `apps/web`: App Router, TypeScript, Tailwind, komponen Button pola shadcn/Radix, React Hook Form, Zod, browser tests.
- `apps/api`: FastAPI, Pydantic, SQLAlchemy, Alembic, Argon2id, CryptoProvider, explicit DTO/policy.
- `scripts`: konfigurasi, DB lab, import/provision/grants, verification, rekey, backup/restore, benchmark.
- `docs`: [arsitektur](docs/ARCHITECTURE.md), [operasional](docs/OPERATIONS.md), [ancaman & batas kontrol](docs/SECURITY.md), [skenario demo](docs/DEMO.md), [kinerja](docs/PERFORMANCE.md).
- [DECISIONS.md](DECISIONS.md): keputusan, termasuk PostgreSQL sesuai permintaan dan perbedaan ketentuan dua PDF panitia. Tidak mengklaim semua persyaratan MySQL dipenuhi PostgreSQL.

`ENCRYPTION_KEYS`, `BLIND_INDEX_KEY`, credential DB, password dan backup recovery key tidak boleh masuk Git, dump, log, browser storage, atau laporan. Simpan recovery key terpisah dari ciphertext sebelum deployment. Lihat [batas keamanan](docs/SECURITY.md): tidak ada klaim production-ready, full disk encryption, live Transit/TLS, RLS, MFA, retensi otomatis atau audit anti-DBA.

Referensi teknis utama: [Next.js App Router](https://nextjs.org/docs/app), [FastAPI](https://fastapi.tiangolo.com/), [SQLAlchemy](https://docs.sqlalchemy.org/en/20/), [cryptography AESGCM](https://cryptography.io/en/latest/hazmat/primitives/aead/), [OpenBao Transit API](https://openbao.org/api-docs/secret/transit/). Dependensi langsung dipin; lockfile frontend menyertakan transitif. Kode mengikuti LICENSE MIT yang sudah ada. Dataset panitia tidak didistribusikan dan tetap mengikuti ketentuan kompetisi.
