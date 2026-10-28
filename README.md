# Pelindungan Data Pribadi ketika Database Bocor

Prototipe Tim BOGAGOL untuk Final Hackathon DPR RI 2026: menemukan data pribadi,
melindungi nilai sensitif, membatasi akses aplikasi, serta menguji kebocoran,
kinerja dan pemulihan. Studi kasus memakai data sintetis panitia.

**Jalur aktif:** Next.js + FastAPI di `app/`, PostgreSQL **18** di `pg-dpr:5433`,
OpenBao **2.5.5** dengan TLS. Format enkripsi dan kewenangan mengikuti
[kontrak teknis](docs/contracts/CONTRACT.md). Enkripsi field AES-256-GCM memakai DEK
per record/domain dan AAD; exact lookup menggunakan blind index HMAC.

## Mulai membaca

| Kebutuhan | Dokumen |
|---|---|
| Peta dokumentasi dan luaran | [Indeks dokumentasi](docs/README.md) |
| Arsitektur dan batas kepercayaan | [Arsitektur](docs/architecture/README.md) |
| Instalasi VM baru | [Paket PostgreSQL/OpenBao TLS](infra/vm/README.md) |
| Menjalankan aplikasi | [README Service App](app/README.md) |
| Server yang sudah berjalan | [Rilis A5](app/docs/DEPLOY_A5.md), [pemulihan](app/docs/RECOVERY.md) |
| Perintah uji dan reproduksi | [Panduan reproduksi](docs/operations/REPRODUCTION.md) |
| Bukti yang mendukung klaim | [Indeks evidence](docs/evidence_index.md) |
| Pekerjaan sebelum submit | [Checklist pengumpulan](docs/submission/CHECKLIST.md) |
| Konteks penulisan laporan | [Konteks laporan](docs/report/CONTEXT.md) |
| Risiko yang masih tersisa | [Keterbatasan](docs/security/LIMITATIONS.md) |

## Status dan cakupan bukti

- Toolkit, profile, migrasi, role/RLS, backup/restore, rotasi kunci, dan aplikasi
  mempunyai kode dan evidence. Setiap hasil harus dibaca bersama dataset/lingkungannya.
- Acceptance setelah A5 lulus **143 pemeriksaan** pada lab PG18/OpenBao TLS dengan
  **17 record buatan sendiri**, termasuk restore dan Chrome nyata.
- Deployment web lulus **100 pemeriksaan** dengan enam akun existing, tanpa mutasi
  data anggota; konfigurasi SQL/TLS internal VM tidak diperiksa langsung lewat SSH.
- Benchmark yang ada pada snapshot ini adalah **baseline awal**. Hasil protected,
  leakage, dan pekerjaan lain di branch anggota tim belum otomatis menjadi bagian paket.
- Laporan PDF, slide final, review manusia, dan akses folder pengumpulan harus
  difinalisasi tim. Ini belum merupakan klaim seluruh persyaratan lomba sudah selesai.

Bukti: [ringkasan acceptance](evidence/acceptance/post-a5-summary.json).
Jangan memakai evidence prototipe lama atau hasil mock sebagai pengganti pengujian nyata.

## Struktur proyek

```text
app/             Service App aktif: backend, frontend, provisioning dan test B
infra/           OpenBao/TLS, PostgreSQL, role bootstrap, acceptance, alat pengumpulan
scanner/         Inventarisasi, klasifikasi dan evaluasi deteksi
policy/          Protection profile dan keputusan per kolom
migration/       Migrasi ke database baru, resume dan decrypt-and-compare
sql/             Skema baseline/protected dan role minimum
scripts/backup/  Backup streaming terenkripsi, restore, tamper dan retention drill
toolkit/         Paket Python dprcrypto
benchmark/       Pengukuran performa; baca status dan scope tiap hasil
datagen/         Dataset sintetis reproducible
verify/          Verifikasi; fitur yang belum tersedia ditandai pada checklist
docs/            Dokumentasi dan bahan pengumpulan
evidence/        Hasil mesin dengan scope; bukan tempat rahasia/dump
archive/         Dokumen/evidence lama, dikecualikan dari paket pengumpulan
```

Path modul aktif dipertahankan agar skrip, deployment dan pekerjaan tim tetap kompatibel.
Runtime PG17 yang lama sudah dihapus dari snapshot; lihat [catatan struktur](docs/submission/STRUCTURE.md).

## Menyiapkan lingkungan pengembang

Python **3.11+**, Git untuk checkout/test, Node.js yang mendukung Next.js proyek, Docker Engine/Compose V2
untuk stack container, dan Google Chrome untuk acceptance browser. Jalankan dari root:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r infra/requirements.txt
.venv/Scripts/python -m pip install -r app/requirements.txt
.venv/Scripts/python -m pip install -r infra/submission/requirements.txt
.venv/Scripts/python -m pip install -e toolkit
Push-Location app/web
npm ci
npm run build
Pop-Location
```

Scanner/datagen/benchmark memiliki requirements tersendiri. Gunakan environment modul
untuk reproduksi yang ketat karena sebagian pin versinya berbeda; lihat
[panduan reproduksi](docs/operations/REPRODUCTION.md) dan [SBOM](docs/sbom/README.md).

Untuk **VM baru**, ikuti [runbook fresh VM](infra/vm/README.md). Untuk **database
existing**, inventaris dahulu dan gunakan upgrade spesifik; jangan mengulang init,
import, prepare/provision, atau mengganti material kunci yang sudah dipakai.
Aplikasi memakai environment eksplisit; contoh ada di [app/.env.example](app/.env.example).

## Pengujian

```powershell
# Default pytest menjalankan suite inti A; integrasi eksternal tetap opt-in.
.venv/Scripts/python -m pytest -q
# B dijalankan terpisah untuk menghindari benturan conftest/import.
.venv/Scripts/python -m pytest -c app/pytest.ini app/tests -q
# Validasi struktur dokumentasi dan paket sumber.
.venv/Scripts/python -m infra.submission check
```

Perintah untuk scanner, benchmark, datagen, browser dan acceptance nyata ada di
[panduan reproduksi](docs/operations/REPRODUCTION.md). Pengujian tidak menjalankan
benchmark resmi atau mengubah database tim secara otomatis.

## Paket pengumpulan

```powershell
.venv/Scripts/python -m infra.submission sbom
.venv/Scripts/python -m infra.submission check
.venv/Scripts/python -m infra.submission build --output dist/submission
```

Paket berisi source aktif, dokumentasi, evidence dan manifest SHA256. Dataset panitia,
`.git`, environment lokal, kredensial, kunci, dump, cache, arsip lama dan referensi buku
mentah dikecualikan. Build paket tidak berarti paket sudah memenuhi seluruh luaran;
[checklist](docs/submission/CHECKLIST.md) menyebut yang masih perlu diselesaikan.

## Data, lisensi dan atribusi

Kode: [MIT](LICENSE). Dokumentasi orisinal: [CC BY-NC 4.0](LICENSE-DOCS.md).
Komponen pihak ketiga mengikuti lisensi asal; lihat [atribusi](THIRD_PARTY_NOTICES.md).
Dataset panitia hanya untuk kompetisi dan tidak boleh dipublikasikan. Repo tetap PRIVATE.
Simpan password, token, kunci, unseal share, root token dan material pemulihan di lokasi
privat di luar checkout; material tersebut tidak boleh masuk lampiran pengumpulan.
