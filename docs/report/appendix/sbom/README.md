# Lampiran dependensi untuk laporan

Tiga berkas CycloneDX1.6 dalam folder ini dibuat langsung dari requirements,
pyproject, npm lockfile dan Compose pada snapshot kode laporan. Ini terpisah dari
SBOM lama di luar folder report yang belum diperbarui setelah merge.

| Berkas | Isi dan batas |
|---|---|
| [python-declared.cdx.json](python-declared.cdx.json) | Deklarasi runtime/build/test langsung; pin modul yang berbeda tetap terpisah, rentang belum menjadi versi instalasi |
| [frontend-lock.cdx.json](frontend-lock.cdx.json) | Seluruh entri dependency npm lockfile aktif, termasuk development/optional; integrity berasal dari lockfile |
| [infrastructure.cdx.json](infrastructure.cdx.json) | Referensi image Compose, tanpa daftar paket OS dan tanpa asumsi digest image deployment |

Daftar CSV yang mudah diolah berada di [dependencies.csv](../../tables/dependencies.csv).
Jumlah komponen/cakupan berada di [evidence_snapshot.json](../../evidence_snapshot.json).
Validasi skema berada di [schema-validation.json](schema-validation.json).

Inventaris ini bukan audit CVE lengkap, bukan lockfile Python transitif dan bukan
sertifikat lisensi seluruh sistem. Kode tim MIT, dokumentasi orisinal CC BY-NC4.0;
dependency mengikuti lisensi asal. Metadata lisensi npm dicatat bila tersedia,
tanpa menebak lisensi paket yang tidak mendeklarasikannya. Native binary lab dan
paket OS yang dipasang di VM harus diinventaris lagi bila klaim deployment dibuat.
