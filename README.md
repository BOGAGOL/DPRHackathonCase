# DPR Secure Data Management System

## Keputusan infrastruktur terbaru — 27 Oktober 2026

Database proyek memakai **PostgreSQL 18 `pg-dpr`, port host 5433**: `baseline_100k`
untuk MODE=plain dan `protected_734`/`protected_100k` untuk MODE=protected.
OpenBao memakai [Compose Modul A](infra/compose.yaml), TLS port 8200.
Panduan terkini: [TLS pg-dpr dan clone development](infra/postgres/README.md).
Instruksi PostgreSQL 17/port 554xx pada bagian lab di bawah adalah sistem lama;
pengalihan konfigurasi API/MODE dikerjakan Modul B. Benchmark resmi tetap pada
laptop pemilik baseline; clone laptop Alby memakai evidence/development terpisah.

Aplikasi layanan Next.js + FastAPI untuk melihat, mencari, dan memperbarui data anggota sesuai hak akses. Ini prototipe hackathon dengan dataset sintetis, bukan situs resmi DPR atau Privacy Scanner. Kode scanner/artefak Task 1 di luar checkout tidak diubah.

Sudah dijalankan pada Windows: PostgreSQL baseline/protected terpisah, import **734 × 29** tanpa perubahan nilai, autentikasi, role/record/field authorization, AES-256-GCM, blind lookup, edit kontak, audit, browser flows, backup/restore, dan benchmark tiga pengulangan termasuk **10.000 record sintetis baru**. Status dan evidence rinci ada di [PROGRESS.md](docs/legacy-md_zhafif/PROGRESS.md) dan [evidence/README.md](docs/legacy-md_zhafif/evidence/README.md). Docker Compose tervalidasi konfigurasinya; container runtime belum diuji karena Docker Engine tidak aktif. Live OpenBao dan TLS deployment: **NOT TESTED**.

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

`api` memakai `app_user`, tanpa kredensial owner/baseline. `tools` adalah CLI terpisah untuk operasi privileged, source mount read-only, tidak ada route scanner/baseline. Baseline hanya aktif dengan profile lab dan network berbeda. Port DB hanya loopback. Compose ini development HTTP/local AES; pengaturan HTTPS/TLS/Transit dijelaskan dalam [runbook](docs/legacy-md_zhafif/docs/OPERATIONS.md). Jangan menggunakan `docker compose down -v` untuk menghentikan lab yang datanya perlu disimpan.

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
- `docs`: [arsitektur](docs/legacy-md_zhafif/docs/ARCHITECTURE.md), [operasional](docs/legacy-md_zhafif/docs/OPERATIONS.md), [ancaman & batas kontrol](docs/legacy-md_zhafif/docs/SECURITY.md), [skenario demo](docs/legacy-md_zhafif/docs/DEMO.md), [kinerja](docs/legacy-md_zhafif/docs/PERFORMANCE.md).
- [DECISIONS.md](docs/legacy-md_zhafif/DECISIONS.md): keputusan, termasuk PostgreSQL sesuai permintaan dan perbedaan ketentuan dua PDF panitia. Tidak mengklaim semua persyaratan MySQL dipenuhi PostgreSQL.

`ENCRYPTION_KEYS`, `BLIND_INDEX_KEY`, credential DB, password dan backup recovery key tidak boleh masuk Git, dump, log, browser storage, atau laporan. Simpan recovery key terpisah dari ciphertext sebelum deployment. Lihat [batas keamanan](docs/legacy-md_zhafif/docs/SECURITY.md): tidak ada klaim production-ready, full disk encryption, live Transit/TLS, RLS, MFA, retensi otomatis atau audit anti-DBA.

Referensi teknis utama: [Next.js App Router](https://nextjs.org/docs/app), [FastAPI](https://fastapi.tiangolo.com/), [SQLAlchemy](https://docs.sqlalchemy.org/en/20/), [cryptography AESGCM](https://cryptography.io/en/latest/hazmat/primitives/aead/), [OpenBao Transit API](https://openbao.org/api-docs/secret/transit/). Dependensi langsung dipin; lockfile frontend menyertakan transitif. Kode mengikuti LICENSE MIT yang sudah ada. Dataset panitia tidak didistribusikan dan tetap mengikuti ketentuan kompetisi.

# juara1onno

## Scanner

Scanner lokal semi-otomatis menemukan kandidat data pribadi melalui isi sampel,
nama kolom, kamus, bentuk nilai, teks bebas, dan relasi. Hasil wajib ditinjau
manusia. Seluruh implementasi, konfigurasi, dan pengujian ada di `scanner/`.
Tidak ada layanan klasifikasi eksternal. Koneksi memakai transaksi read-only;
dump SQL hanya diparse, tidak dieksekusi.

Gunakan Python 3.11+ dan GNU Make. Di PowerShell, instal dan aktifkan environment:

```powershell
python -m venv scanner/.venv
.\scanner\.venv\Scripts\Activate.ps1
make scanner-install
```

Administrator membuat role melalui `scanner/sql/scanner_role.sql` (sekali saja):

```powershell
psql -X -W -h 127.0.0.1 -p 5433 -U postgres -d postgres -f scanner/sql/scanner_role.sql
```

Skrip meminta password role lewat Python `getpass` yang ditangkap langsung ke
variabel psql `:'scanner_password'`. Aktifkan environment Python terlebih dahulu.
Jangan menaruh password di argumen, kode, atau riwayat
terminal. Audit hak `PUBLIC` terlebih dahulu: `NOINHERIT` tidak menghapus hak
`PUBLIC`. Skrip hanya memberi CONNECT, USAGE public, dan SELECT public.anggota;
tidak memberi akses otomatis ke tabel baru. Sesuaikan daftar GRANT untuk sumber
lain setelah ditinjau administrator. Panduan rinci dan pemeriksaan hak ada di
[scanner/NOTES.md](scanner/NOTES.md).

Isi kredensial hanya melalui environment `SCANNER_DATABASE_URL`. Contoh aman
berbasis prompt tanpa menuliskan password tersedia di NOTES. `.env` tidak dibaca
otomatis dan sudah diabaikan Git. Jalankan:

```powershell
make scanner-test
make scan LABEL=before
make scan-dump FILE=path/ke/dump.sql LABEL=before
python -m scanner files --file path/ke/aplikasi.log path/ke/ekspor.csv --label before --out results/scanner/files-before
```

Tanpa Make, gunakan `python -m pip install -r scanner/requirements.txt`,
`python -m pytest scanner/tests -q`, dan
`python -m scanner db --schema public --sample 1000 --label before --out results/scanner/before`.
Mode dump menggunakan `python -m scanner dump --file path/ke/dump.sql --label before --out results/scanner/dump-before`.
`--sample` membatasi sampel per tabel dan hasil teks per file (default 1000).
`--label after` memakai `environment_after.yaml`; label lain harus mempunyai
konfigurasi environment atau menentukan `--environment path.yaml`.
Tiga faktor lingkungan (volume, exposure, recovery) dalam contoh adalah asumsi
yang harus diverifikasi. Sensitivitas dan dampak per jenis diatur melalui
`scanner/config/impact.yaml` (opsional `--impact path.yaml`). Dengan faktor
before 3/5/5, skor minimum adalah 16 (P2); P3 membutuhkan faktor lingkungan
lebih rendah yang memang terverifikasi, seperti contoh after.

Setiap scan menghasilkan `inventory.csv`, `relations.json`, `k_anonymity.json`,
`run_meta.json`, dan `report.html` statis tanpa JS eksternal. `features.json`
menyimpan semua fitur agregat dan bukti negatif; mode files juga menghasilkan
`findings.csv` berisi file, nomor baris, jenis, dan nilai termasking. Hasil berada
di `results/` yang diabaikan Git. Semua sampel dimasking, termasuk pada laporan
HTML dan temuan relasi; nilai pengelompokan k-anonymity tidak dikeluarkan.

Arti kolom `inventory.csv`:

| Kolom | Arti |
| --- | --- |
| `table`, `column`, `data_type` | Sumber, nama kolom, tipe penyimpanan |
| `detected_type` | Kandidat jenis data berdasarkan sinyal gabungan |
| `pdp_class` | Kandidat umum, spesifik, atau non_pribadi |
| `risk_level` | rendah, sedang, tinggi, kritis, dari rentang prioritas |
| `priority`, `priority_score` | P0–P3 dan total enam faktor (6–30) |
| `f_sensitivity`, `f_impact` | Faktor 1–5 per jenis dari impact.yaml |
| `f_exploitability` | Faktor 1–5 dari bukti isi; kategori, operasional, dan hitungan keluarga bernilai 1 |
| `f_volume`, `f_exposure`, `f_recovery` | Faktor 1–5 dari konfigurasi lingkungan |
| `content_score`, `name_score`, `confidence` | Skor jenis terpilih; bobot default 80% isi + 20% nama |
| `triage` | auto_accept, needs_review, atau low_confidence; semuanya tetap dilaporkan |
| `derived_from` | Kandidat sumber duplikat/turunan, dipisahkan titik koma |
| `consistent_protection_with` | Kolom sumber yang membutuhkan perlakuan masking/akses konsisten |
| `sample_masked` | Maksimal tiga contoh termasking |
| `reason` | Alasan berbasis fitur, bukti negatif, dan pertanyaan retensi |
| `recommendation` | Turunan: review_minimization; nama publik: retain+mask_for_analyst; tanggal lahir: generalize_for_analyst; password: hash Argon2id; jenis lain: proteksi sesuai konteks |
| `allowed_roles`, `search_need` | Default konfigurasi untuk revisi manusia |

Agama dipetakan sebagai umum dan ditandai rawan diskriminasi; data keuangan
pribadi, kesehatan, biometrik, genetika, catatan kejahatan, dan data anak sebagai
spesifik, mengikuti [UU PDP Pasal 4](https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022).
Klasifikasi kandidat tidak menggantikan penilaian konteks oleh tim.

Salin `scanner/ground_truth.template.csv` ke `scanner/ground_truth.csv`, isi manual
oleh anggota tim, lalu jalankan `make scan-eval LABEL=before`. Evaluasi mengukur
precision/recall/F1 personal, akurasi jenis dan kelas, confusion matrix, serta
false positive/negative pada output mentah sebelum koreksi manusia. Bandingkan
dengan `--baseline regex_only` pada perintah db/dump/files dan direktori output
terpisah. `low_confidence` tetap dihitung sebagai kandidat personal kecuali
kelasnya `non_pribadi`; keputusan ini tercantum di hasil evaluasi.

Keterbatasan: relasi dan deteksi jenis memakai sampel; kamus dan heuristik dapat
keliru. Format/enkripsi tidak membuktikan anonimitas. k-anonymity memakai agregat
seluruh tabel database atau seluruh dump, terbatas kombinasi 1–3 kolom kandidat;
NULL dikelompokkan bersama. Mode teks bebas tidak mempunyai k-anonymity. Parser
mendukung literal INSERT MySQL/PostgreSQL dan COPY teks PostgreSQL; ekspresi SQL,
COPY CSV/biner, dump arsip, serta beberapa ekstensi dialect ditolak. Mode dump
menaruh plaintext sementara di disk lokal sebelum dihapus. Detail keputusan,
hasil pengujian, batasan, dan validasi database asli: [scanner/NOTES.md](scanner/NOTES.md).

Versi 1.1.0 mengenali NIK berpanjang tidak baku hanya dengan dukungan isi dan
kata kunci nama; tanpa konteks nama tetap kandidat identifier. Nama berkardinalitas
rendah menjadi kategori, tanggal pernikahan dibedakan dengan pola tanggal/NULL
bersyarat, dan hitungan keluarga tetap umum serta needs_review. ID integer
berurutan pada sampel menjadi kandidat kunci penghubung operasional. Sumber
functional dengan rasio unik non-NULL >0.9 dilaporkan terpisah pada
`near_unique_quasi_identifiers`. Report menyediakan tabel ringkas dan cetak A4
landscape; k-anonymity diurutkan 1–3 kolom, maksimal 15 kombinasi minimal di HTML,
sementara semua agregat tetap di JSON. Setiap run mencatat versi, ringkasan
perubahan, dan kebijakan prioritas yang dipakai. Simpan run v1.1 di folder baru
agar hasil `before_v1/` tetap dapat dibandingkan.

## Data sintetis Modul C (kontrak PostgreSQL 18)

Generator baseline 100k sesuai kontrak tersedia di `datagen/`, terpisah dari generator lab historis
`scripts/scale_lab.py`. Panduan PowerShell dan prompt password aman ada di
[datagen/README.md](datagen/README.md); keputusan dan batas ada di [datagen/NOTES.md](datagen/NOTES.md).
Jalankan `python -m datagen --rows 100000 --seed 42 --target-db baseline_100k` dari environment datagen
setelah credential env disetel. Jika database sudah ada, gunakan
`python -m datagen validate --db baseline_100k --rows 100000`; generate menolak overwrite.
Sumber `postgres`/734 baris tetap hanya dibaca. Snapshot/credential berada di luar repo melalui
`DPR_PRIVATE_DIR`; ringkasan mesin ke `evidence/datasets/`, raw lokal ke `results/`.
Target yang disahkan sebelum benchmark: [docs/targets.md](docs/targets.md), dengan bukti commit
di [evidence/targets_commit.json](evidence/targets_commit.json). Benchmark baru dan restore drill
Modul C dijalankan pada langkah berikutnya, setelah baseline tervalidasi.

## Policy dan skema protected (Modul A, tahap 3)

Profile dari inventory scanner dan override kontrak: [policy/NOTES.md](policy/NOTES.md).
Penerapan skema/role ke `pg-dpr:5433` dan handoff Service App:
[sql/protected/NOTES.md](sql/protected/NOTES.md),
[sql/roles/NOTES.md](sql/roles/NOTES.md). Tahap ini menyiapkan database protected;
migrasi data dijalankan pada tahap berikutnya.
