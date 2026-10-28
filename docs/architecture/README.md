# Arsitektur dan aliran data

![Arsitektur sistem](architecture.svg)

Sumber diagram: [Mermaid](architecture.mmd), [SVG](architecture.svg),
[PNG resolusi tinggi](architecture.png) untuk dokumen/slide.
Diagram menunjukkan rancangan aktif, bukan bukti seluruh konfigurasi internal VM
telah diperiksa. Reverse proxy/service manager bergantung instalasi operator.

## Komponen dan kewenangan

| Komponen | Data/kemampuan yang diperlukan |
|---|---|
| Browser | DTO yang diizinkan, cookie sesi; tanpa DEK, token Bao atau credential DB |
| Next.js | UI dan proxy same-origin; koneksi API HTTPS terverifikasi |
| FastAPI | Autentikasi, scope/field policy, masking, audit dan pemrosesan field di memori |
| dprcrypto | AES-256-GCM/AAD, DEK per record/domain, HMAC bidx dan cache DEK TTL/ukuran terbatas |
| app_user | Operasi anggota/aplikasi, NOBYPASSRLS, tanpa DDL; principal SET LOCAL per transaksi |
| analyst_user | SELECT analyst_summary dan fungsi agregat tersupresi; tanpa raw view/tabel |
| auditor_user | Metadata audit; tanpa data anggota |
| PostgreSQL 18 | Ciphertext, wrapped DEK, bidx, REF/age_band, akun/sesi/scope/audit |
| OpenBao Transit | pii-kek, finance-kek, search-hmac; token policy TTL, TLS dan manual unseal |
| backup_user | pg_dump read minimum, tidak mempunyai kemampuan decrypt OpenBao |
| Operator migrasi/rotasi | Capability sementara sesuai peran; root bukan identitas runtime |

Token svc-app dapat unwrap PII dan FIN; pemilihan field keuangan menurut role
pengguna ditegakkan backend, bukan oleh Transit yang mengetahui endpoint/user HTTP.
Enkripsi field berlangsung lokal dengan DEK; `context` Transit tidak dipakai sebagai
pengganti AAD field. Dukungan associated_data Transit tidak menjadi syarat desain.

## Jalur baca, tulis dan pemulihan

1. Browser mengirim permintaan lewat HTTPS dan cookie sesi; backend memeriksa role,
   principal/scope, record dan allowlist field sebelum merilis respons.
2. Exact lookup membuat HMAC kolom yang dinormalisasi. Record membawa wrapped DEK;
   unwrap melalui TLS OpenBao, lalu GCM memverifikasi AAD record/kolom/versi di memori.
3. Insert/update membuat/enkripsi field menurut profile dan memperbarui bidx; NULL
   tetap NULL. Kegagalan dekripsi menghasilkan error generik, tanpa fallback.
4. Analytics menjalankan query marginal yang sudah disupresi SQL; kelompok <5 tidak
   memberi label atau count. Frontend tidak menerima proyeksi anggota mentah.
5. pg_dump mengalir ke enkripsi backup; manifest HMAC dan digest dipakai sebelum
   restore ke DB baru. Setelah validasi/hardening ACL, operator melakukan cutover.

Urutan kripto: [data-lifecycle.mmd](data-lifecycle.mmd). Kunci backup/HMAC berbeda
dari domain data dan tidak disimpan bersama arsip. Material unseal/recovery berada
di storage privat operator, bukan di DB atau paket sumber.

## Batas lab dan produksi

Baseline plaintext dan source 734 dipertahankan pada instance lab untuk eksperimen.
Pengecualian non-TLS hanya bench/scanner pada baseline dari satu IP terkonfigurasi;
protected dan restore tetap wajib TLS. Diagram tidak mengklaim seluruh pg-dpr,
filesystem, memory, log atau material sumber telah terenkripsi. Pemisahan plane
secara logis di satu VM juga bukan isolasi fisik ketika OS/seluruh credential dikuasai.
