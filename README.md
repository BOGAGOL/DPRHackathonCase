# Pelindungan Data Pribadi ketika Database Bocor

Prototipe **Tim BOGAGOL — Final Hackathon DPR RI 2026**. Scanner menginventarisasi
29 kolom; profile mengendalikan enkripsi 25 kolom dengan AES-256-GCM, envelope DEK
per record/domain, AAD dan tiga blind index. FastAPI + Next.js menerapkan enam
peran, scope record, masking dan analytics dengan suppression k≥5.

## Jalankan demo 734 record

Prasyarat: **Python 3.11+, Node.js ≥20.9/npm, Docker Engine + Compose V2, Google
Chrome**. Dataset panitia `02_data.sql` harus tersedia secara privat; tidak
termasuk paket sumber untuk publik. Dari root checkout:

```powershell
python -m infra.reproduce setup
python -m infra.reproduce verify --data "C:/private/02_data.sql"
python -m infra.reproduce demo --data "C:/private/02_data.sql"
```

Di Linux gunakan path dataset Linux. Alternatif GNU Make yang tersedia:
`make setup`, `make verify DATA=/private/02_data.sql`, `make demo DATA=/private/02_data.sql`.
Variabel `DPR_DEMO_DATA` juga dapat menunjuk input privat. Jika dataset private-repo
ada pada `sql/baseline/02_data.sql`, argumen `--data` boleh dihilangkan.

`verify` menjalankan **setup service → import → assessment → hardening → enam akun
aplikasi → verifikasi keamanan/browser → backup/restore → cleanup service**.
`demo` menjalankan pemeriksaan yang sama lalu menahan aplikasi HTTPS sampai Ctrl+C.
Semua service milik run baru pada port loopback acak; tidak menyentuh pg-dpr,
server deployment atau database/evidence benchmark existing. Kredensial hanya
pada folder privat di luar repo. Hasil baru: `evidence/reproduction/<run-id>/`.

**[Panduan reproduksi lengkap](docs/operations/REPRODUCTION.md)** menjelaskan
prasyarat, sertifikat browser, lokasi akun, jalur native jika Docker tidak tersedia,
troubleshooting, unit test, operasi existing dan benchmark terpisah.

## Peta repository

| Lokasi | Isi |
|---|---|
| `scanner/`, `policy/` | Assessment, klasifikasi, override dan protection profile |
| `toolkit/`, `migration/`, `sql/` | Kripto v1, migrasi resumable, skema, ACL/RLS |
| `app/` | Backend/frontend, provisioning, enam peran dan pengujian |
| `infra/`, `scripts/backup/` | TLS/OpenBao, launcher reproduksi, rotasi, backup/restore |
| `datagen/`, `benchmark/`, `verify/` | Pembesaran data, kinerja, leakage/security verification |
| `evidence/` | Hasil mesin dan raw historis dengan cakupan/lingkungan masing-masing |
| `docs/` | [Indeks](docs/README.md), laporan, presentasi, arsitektur, runbook dan SBOM |
| `archive/` | Riwayat prototipe; tidak dipakai runtime/paket submission |

## Bukti dan batas klaim

Migrasi 734/100k/1M, leakage dan perbandingan DB before/after sudah tersedia;
baca [indeks evidence](docs/evidence_index.md). **Benchmark DB belum memenuhi target
latensi/throughput**; keberhasilan keamanan bukan kelulusan target kinerja.
Bukti web, lab, native dan VM mempunyai scope berbeda. Status benchmark API
mengikuti evidence sesi; jangan menyebut rencana/percobaan setup sebagai hasil ukur.

Daftar 15 luaran dan pekerjaan final: **[checklist submission](docs/submission/CHECKLIST.md)**.
Laporan Markdown/konteks presentasi belum merupakan PDF laporan/slide final.
[Keterbatasan](docs/security/LIMITATIONS.md) meliputi equality leakage, metadata REF/NULL,
kompromi aplikasi+kunci, retensi backup lama, custody dan DR key-plane.

Kode [MIT](LICENSE), dokumentasi [CC BY-NC 4.0](LICENSE-DOCS.md), komponen pihak
ketiga mengikuti [atribusi](THIRD_PARTY_NOTICES.md). Dataset panitia tidak boleh
dipublikasikan; repo tetap **PRIVATE**, termasuk riwayatnya. Tidak ada secret di lampiran.
