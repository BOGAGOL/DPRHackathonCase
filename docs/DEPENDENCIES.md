# Dependency inventory

Runtime yang diuji: Python3.11.5, PostgreSQL18.6, OpenBao2.5.5, cryptography50.0.2,
FastAPI0.134.0, Node22.10.0. Versi aktual per lingkungan dapat berbeda; requirements
A/B dan C dipasang di environment terpisah karena pin psycopg berbeda.

SBOM CycloneDX1.6 tersedia di docs/sbom:

- python-declared.cdx.json: deklarasi dependency langsung/runtime/build/test.
- service-web-lock.cdx.json: seluruh entry lockfile frontend termasuk development/optional.
- infrastructure.cdx.json: image Compose dan lokasi deklarasi.
- python-env.cdx.json dan BOM/audit per komponen: snapshot environment/audit yang
  dicatat pada saat pembuatannya, bukan inventaris seluruh VM/OS/container.

Cryptography menggunakan ≥50.0.2,<51. Tidak ada penggunaan langsung PolicyBuilder,
x509.verification atau pkcs7 pada scope review toolkit/infra/scripts/app/migration/
benchmark/verify yang dicatat. Upgrade wheel tidak memperbarui OpenSSL CPython/OS.
Audit dengan nol advisory hanya menyatakan temuan database advisory pada waktunya,
bukan sertifikasi tidak ada kelemahan. Tag postgres:18 belum berupa digest immutable.

Regenerasi deklarasi: `python -m infra.distribution sbom`. Generator mempertahankan
range yang belumresolved; tidak mengarang versi transitif. `check` memeriksa hash
input dan hash BOM. Lisensi yang tidak tersedia tidak ditebak.
