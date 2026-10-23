# Progres aplikasi layanan — 23 Oktober 2026 WIB

Target kerja: `web_user/juara1onno`. Scanner Task 1 dan dataset sumber tidak diubah.

| Fase | Implementasi | Verifikasi |
|---|---|---|
| 1 Foundation | IMPLEMENTED | TESTED native Windows/PostgreSQL; Compose config PASS, container runtime NOT TESTED |
| 2 Database/import | IMPLEMENTED | TESTED PostgreSQL: 734 × 29, equality seluruh field, import rerun, Alembic drift check |
| 3 Auth/authorization | IMPLEMENTED | TESTED API/Chromium; role + assignment + field, CSRF, expiration/revoke, Argon2id |
| 4 Protection | IMPLEMENTED local / Transit adapter | TESTED AES-GCM/HMAC/metadata/tamper/key/AAD; Transit contract+outage mock only |
| 5 Application | IMPLEMENTED | TESTED build dan 5 browser flows; login, dashboard, list, lookup, detail, PATCH, audit/admin |
| 6 Security tests | IMPLEMENTED | 33 Pytest PASS; live PostgreSQL grant/dump/API checks PASS; 5 Chromium PASS |
| 7 Benchmark/docs | IMPLEMENTED lab | 734 dan 10.000 record, masing-masing 3 repeats + raw results + backup/restore; HTTP/TLS benchmark NOT TESTED |

Referensi dibaca: agent pack, README/scanner Task 1 dan inventaris, dua PDF soal, brainstorming terlampir, inventaris ZIP referensi. Shared chat tidak dapat diambil; memakai lampiran.

Blocker awal: Docker Desktop Linux Engine tidak aktif. Pengujian SQLite lokal tidak dianggap bukti PostgreSQL atau Compose end-to-end.

## Hasil sesi implementasi — 2026-10-23 WIB

**Task IDs:** service phases 1–7; layanan lokal dan bukti keamanan/performa lab, bukan penyelesaian seluruh submission kompetisi.

**Files changed:** aplikasi baru `apps/web`, `apps/api`, Alembic migrations, `scripts`, `tests`, `infrastructure`, Compose, .gitignore/.env.example, README/AGENTS/DECISIONS, docs/evidence. Dataset, Task1 scanner/outputs, agent pack dan arsip panitia tidak diubah. Tidak membuat commit atau publikasi.

**Implementasi:** dua server PostgreSQL baru `.local/pg-protected` (55432) dan `.local/pg-baseline` (55433), terpisah dari instance yang sudah ada. API `app_user` memiliki grant minimum. AES-256-GCM pada 27 field, key+HMAC terpisah, AAD record/field, enkripsi versi, no fallback. Empat akun demo berpassword acak di `.local/demo-accounts.json`, no hardcode. Admin tidak memiliki record data secara otomatis. Schema protected tidak memiliki kolom KTP plaintext. Source parser tidak mengeksekusi SQL dan preserving quoted NULL/numeric string/leading zero.

**Perintah dan exit code akhir:**

| Perintah | Exit / hasil | Evidence |
|---|---|---|
| `.venv/Scripts/python -m alembic -c apps/api/alembic.ini upgrade head` | 0 | Schema PostgreSQL dan migration version 0001 |
| `.venv/Scripts/python -m alembic -c apps/api/alembic.ini check` | 0; no new upgrade operations | Migration/schema drift check |
| `scripts/manage.py grants` | 0 | `postgres-security.json` |
| `scripts/manage.py import --source <original SQL>` (termasuk rerun) | 0 | `migration.json` |
| `scripts/manage.py verify --source <original SQL>` setelah browser/benchmark | 0; 734 × 29 equality | `migration.json` |
| `scripts/manage.py provision` | 0 | Credential lokal ignored; empat role live |
| `.venv/Scripts/python -m pytest -q --junitxml=evidence/security-tests.xml` | 0; **33 passed** | `security-tests.xml` |
| `scripts/verify_security.py` | 0; semua checks true | `postgres-security.json` |
| `npm run build` (`apps/web`) | 0; compilation + TypeScript + pages | Build produksi Next 16.4.2 |
| `npm run test:e2e` (`apps/web`) | 0; **5 passed** | `browser-tests.json` (sanitized) |
| `scripts/backup.py drill` | 0; 734 restored, semua field decrypt, tamper rejected | `backup-restore.json` |
| `scripts/benchmark.py --operations 300 --repeats 3 --backup-restore` | 0; zero errors | `benchmark.json` |
| `scripts/scale_lab.py --rows 10000` | 0; generated dan round-trip verified | Database lab baru, tidak menambah source/application data |
| `scripts/benchmark.py --env-file .local/scale.env --operations 300 --repeats 3 --backup-restore --output evidence/benchmark-scaled.json` | 0; zero errors | `benchmark-scaled.json` |
| `docker compose --profile lab --profile tools config --quiet` | 0 | Config saja; engine tidak aktif |
| `scripts/start-local.ps1` / `scripts/stop-local.ps1` | 0; health readiness through Next proxy | Launcher+shutdown native diuji |
| `scripts/export_evidence.py` | 0 | Sanitized browser results, OpenAPI, dependency inventory, PERFORMANCE.md |

Perintah Python `scripts/...` di tabel memakai interpreter `.venv/Scripts/python`. Evidence ada di [evidence](evidence/README.md), tidak berisi nilai record atau secret. Raw browser results/screenshot QA dan semua key/DB/backup hanya `.local` ignored. Screenshot QA dashboard menyamarkan nama. Tidak menyalin raw SQL ke checkout.

**Bug yang ditemukan dan diperbaiki:** parser awal belum menerima literal angka tak berquote; form awal memvalidasi email sumber dummy yang invalid saat mengedit alamat; export komponen non-page dipindahkan dari Next page; Alembic Windows path dengan spasi ditangani lewat `path_separator=os`; `localhost` libpq menunggu IPv6 sehingga konfigurasi lab memakai 127.0.0.1; detail route members membatalkan fetch lama dan mereset state ketika ID berubah; launcher shutdown memakai start-time ticks karena konversi tanggal JSON mengubah format timestamp. Setelah perbaikan, keempat port proyek terbukti tertutup dan restart health check berhasil. Kegagalan sementara tidak dicatat sebagai hasil akhir PASS tanpa rerun.

**Batas yang belum dipenuhi:** container runtime, live OpenBao, TLS browser/API/DB/KMS, full disk/WAL/temp encryption, full HTTP/TLS benchmark, native Transit rotation/rewrap, HMAC rotation tooling, multi-worker distributed limiter, RLS/DB analyst/auditor/backup roles, retention/deletion automation, dual-control permission approval, second-host fresh-clone drill. Ini tetap NOT TESTED/PLANNED, bukan DONE. Laporan PDF/slides kompetisi dan human ground truth Task1 bukan output aplikasi layanan ini. PostgreSQL mengikuti permintaan user; konflik MySQL/submission/durasi dua PDF tetap perlu konfirmasi panitia.

**NEXT:** aktifkan Docker Linux Engine lalu validasi Compose pada volume baru; siapkan PKI dan OpenBao terpisah; jalankan end-to-end TLS/Transit dan outage/rotation/recovery, lalu benchmark HTTP workload setara. Jangan menimpa lab source, mengganti key tanpa recovery copy, atau mempublikasikan dataset/credential.
