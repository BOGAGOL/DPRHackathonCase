# SBOM dan daftar dependensi

Inventaris berformat **CycloneDX 1.6 JSON**, dibuat dari sumber aktif, bukan dari
manifest prototipe lama. Regenerasi: `python -m infra.submission sbom`.

| File | Cakupan |
|---|---|
| [Python](python-declared.cdx.json) | Semua deklarasi langsung runtime/build/test di requirements dan pyproject aktif |
| [Frontend](service-web-lock.cdx.json) | Semua entri package npm lockfile aktif, termasuk development/optional |
| [Infrastruktur](infrastructure.cdx.json) | Referensi image pada Compose aktif dan fixture |
| [Indeks](index.json) | Jumlah komponen, scope, SHA256 LF setiap input |

Python **bukan** inventaris transitif environment deployment. Pin A/B dan C yang
berbeda ditampilkan terpisah; range yang belum terkunci tidak diberi versi palsu.
Frontend mencatat versi/lisensi/integrity dari lockfile, bukan hasil mengunduh dan
memverifikasi ulang setiap tarball. Lisensi tidak ditebak bila metadata tidak ada.
Image PostgreSQL tag 18 belum mengunci patch/digest; OS packages dan image digest
deployment belum masuk inventaris. Binary native acceptance tidak ikut ZIP sumber.

Ini memenuhi fungsi daftar dependensi dengan batas yang disebut, bukan sertifikasi
tidak ada CVE atau bukti seluruh supply chain aman. Audit npm yang ada dibaca sebagai
snapshot terpisah; snapshot audit Python terbaru dijelaskan di bagian berikut; audit container/OS menyeluruh belum dicakup.
Jika tim menginginkan BOM transitif deployment, ekspor dari masing-masing environment
modul dan image yang benar-benar dipakai, pertahankan scope/revisi/waktu pengambilannya.

`python -m infra.submission check` menolak input SBOM yang stale. Perubahan lockfile,
requirements, pyproject atau compose memerlukan regenerasi. Schema resmi:
[bom-1.6.schema.json](https://cyclonedx.org/schema/bom-1.6.schema.json).

---

# SBOM dan audit dependency — 29 Oktober 2026

Source: merge main `4fdd7aa5a87e553f8da1e1397d5d5a772c80a402`.
Environment laptop Windows, Python 3.12.10, cryptography 50.0.2, pytest 9.0.3.
Generator: cyclonedx-bom 7.6.0 dan pip-audit 2.10.1. Versi alat, hash sembilan
JSON (UTF-8, line ending dinormalisasi ke LF agar sesuai Git blob), waktu WIB, dan ringkasan audit ada di
`app/evidence/access-control/dependency-upgrade-sbom-20261029.json`.

| Audit | Dependency yang diperiksa | Temuan | Dependency dilewati |
|---|---:|---:|---:|
| app-python-audit.json | 31 | 0 | 0 |
| benchmark-python-audit.json | 22 | 0 | 0 |
| infra-python-audit.json | 16 | 0 | 0 |
| app-web-audit.json | package-lock npm | 0 | — |

Angka merupakan advisory yang diketahui layanan audit saat dijalankan, bukan
hasil pentest. Berkas audit menyimpan hasil resolusi dependency masing-masing
requirements secara terpisah. Pin psycopg benchmark berbeda dari pin aplikasi;
kedua requirements tidak dipasang bersama dalam satu environment.

`python-env.cdx.json` mencatat environment aktual laptop: app + infra + editable
toolkit serta alat SBOM/audit. Ini bukan inventory seluruh VM/Linux/container.
BOM `*-python.cdx.json` berasal dari deklarasi requirements, bukan hasil resolusi
transitif. Untuk rentang versi, generator mempertahankan constraint dan dapat
tidak mengisi versi tunggal; versi terpasang ada di environment BOM dan hasil
resolusi audit. Web BOM berasal dari package-lock, dengan optional dependency
dikecualikan sesuai perintah yang diminta.

## Regenerasi di PowerShell

Dari root checkout dengan environment terbaru dan alat audit terpasang:

```powershell
.\app\.venv\Scripts\Activate.ps1
cyclonedx-py environment -o docs\sbom\python-env.cdx.json
cyclonedx-py requirements app\requirements.txt -o docs\sbom\app-python.cdx.json
cyclonedx-py requirements benchmark\requirements.txt -o docs\sbom\benchmark-python.cdx.json
cyclonedx-py requirements infra\requirements.txt -o docs\sbom\infra-python.cdx.json
pip-audit -r app\requirements.txt -f json -o docs\sbom\app-python-audit.json
pip-audit -r benchmark\requirements.txt -f json -o docs\sbom\benchmark-python-audit.json
pip-audit -r infra\requirements.txt -f json -o docs\sbom\infra-python-audit.json
Set-Location app\web
npm sbom --package-lock-only --omit optional --sbom-format cyclonedx | Out-File -Encoding utf8 ..\..\docs\sbom\app-web.cdx.json
npm audit --package-lock-only --json | Out-File -Encoding utf8 ..\..\docs\sbom\app-web-audit.json
```

Audit exit 1 dapat berarti ditemukan advisory; baca JSON. Kegagalan jaringan
atau resolusi tidak boleh dicatat sebagai nol temuan. Regenerasi dan periksa pula
hash/ringkasan evidence jika artefak ini berubah.
