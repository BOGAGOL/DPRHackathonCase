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
snapshot terpisah; hasil audit Python/container menyeluruh masih perlu dilengkapi.
Jika tim menginginkan BOM transitif deployment, ekspor dari masing-masing environment
modul dan image yang benar-benar dipakai, pertahankan scope/revisi/waktu pengambilannya.

`python -m infra.submission check` menolak input SBOM yang stale. Perubahan lockfile,
requirements, pyproject atau compose memerlukan regenerasi. Schema resmi:
[bom-1.6.schema.json](https://cyclonedx.org/schema/bom-1.6.schema.json).
