# Threat model

Status: dokumen rancangan berdasarkan implementasi dan evidence pada snapshot ini,
masih perlu review manusia. Fokus simulasi salinan data, bukan eksploitasi jaringan.

## Aset dan pihak

Aset: nilai PII/FIN, DEK per record, wrapped DEK, kunci Transit/HMAC, session/akun,
backup beserta kunci enkripsi/HMAC yang terpisah, audit, dan material recovery.
Pemakai sah: operator, privileged_officer, finance_officer, analyst, auditor dan
anggota. Administrator database dan key-operator mempunyai kewenangan berbeda.

Penyerang yang dibahas: pemegang dump/backup tanpa kunci; pemegang salah satu
kemampuan domain PII/FIN/search; pemakai aplikasi yang mencoba record/field di luar
izin; pencuri credential role database; serta kompromi aplikasi bersama key plane.

## Batas kepercayaan

Browser menerima DTO yang diizinkan; masking dilakukan di backend. Frontend dan
API berkomunikasi lewat HTTPS, koneksi API-PostgreSQL memakai verify-full dan CA,
OpenBao memakai TLS dengan CA eksplisit. Identitas aplikasi dipetakan ke scope
record; role DB layanan berbeda untuk data, analytics dan audit. Database hanya
menyimpan wrapped DEK, ciphertext, blind index dan REF yang disepakati.

RLS menambah lapisan pembatasan tetapi `app.principal` adalah setting transaksi
yang bisa dipalsukan pencuri credential app_user. Key plane/logical role separation
bukan isolasi fisik otomatis bila seluruh VM atau akun OS dikuasai.

| Ancaman | Kontrol yang diimplementasikan | Bukti/batas |
|---|---|---|
| Dump membuka PII/FIN | Field AEAD, envelope per record/domain | Codec/vector/migrasi diuji; leakage artefak menyeluruh di snapshot ini masih parsial |
| Backup dibaca tanpa kunci arsip | Streaming AES-GCM, kunci backup terpisah | Restore dua mode/tamper/retensi; salinan kunci harus dijaga terpisah |
| Bit ciphertext diubah atau ditukar | Tag GCM dan AAD record/kolom/versi | Test tamper/swap fail-closed; tidak melindungi aplikasi yang telah dikuasai |
| Enumerasi exact lookup nilai berentropi rendah | HMAC blind index dengan key plane | Equality/frequency tetap bocor; search capability dapat dipakai dictionary attack |
| Pengguna membuka record orang lain | Backend predicate, binding anggota, access_scope + RLS | Acceptance nyata mencakup IDOR; bukan sertifikasi semua assignment/populasi |
| Role memperoleh field FIN/PII berlebih | Allowlist DTO per peran; server masking | JSON mentah diuji; svc-app sendiri dapat unwrap kedua domain sehingga backend tetap dipercaya |
| Analyst membaca record/kelompok kecil | Raw view/table ditolak; marginal HAVING count(*)>=5 | SQL 42501 dan label singleton diuji; bukan DP/k-anonymity gabungan |
| SQL injection/CSRF/XSS/session theft | Parameterisasi, validasi, CSRF, CSP nonce, secure/httpOnly/SameSite cookie | B unit+scope acceptance; tidak mengklaim seluruh serangan web telah tercakup |
| Log/temp/browser menyimpan nilai asli | No-store, DTO minimal, storage kosong, log terbatas | Browser diperiksa; scan seluruh log/history host belum selesai |
| Kunci hilang | Unseal shares, custody privat, prosedur recovery | Unseal/restore data diuji; DR seluruh key-plane lintas mesin belum dibuktikan |
| Credential app_user dicuri | Hak minimum, NOBYPASSRLS, tanpa DDL | Attacker masih dapat mengubah principal setting; backend auth tidak lagi menjadi batas tunggal |
| DBA/OS/key plane dan aplikasi dikuasai | Pemisahan peran dan revokasi mengurangi blast radius | Kerahasiaan tidak dijamin jika seluruh kemampuan decrypt/data ikut dikuasai |
| Seluruh storage lab dicuri | AEAD pada target protected, backup terenkripsi | Source/baseline/known-values plaintext harus dihitung terpisah; physical/WAL leak belum diuji |

## Keputusan dan pekerjaan tersisa

Tidak mengenkripsi semua kolom: REF dan age_band mempertahankan fungsi agregat,
dengan leakage yang dicatat. Tidak menghapus tiga kolom nama identik pada migrasi;
minimisasi hanya rekomendasi karena kontrak mempertahankan nilai sumber.
Role key-operator tidak membawa credential DB; admin_user bukan decrypt identity.
Root/unseal material bukan credential aplikasi dan tidak masuk paket pengumpulan.

Sebelum final: review manusia, masukkan hasil leakage/benchmark resmi yang benar,
lengkapi scan S05/S06, uji artefak fisik terisolasi bila diklaim, serta praktikkan
recovery key-plane dan pemusnahan arsip menurut [operasional](../operations/OPERATIONS.md).
Seluruh risiko tersisa dirangkum pada [keterbatasan](LIMITATIONS.md).
