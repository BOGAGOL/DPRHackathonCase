# Prompt Modul A: Infra + Crypto + Migrasi + Role + Backup (pemilik: Alby)

Baca `AGENTS.md` dan `docs/contracts/CONTRACT.md` terlebih dahulu. Kerjakan tahap demi tahap,
commit-able per tahap, dan jalankan test setiap tahap. Folder milikmu: `infra/`, `toolkit/`,
`policy/`, `migration/`, `sql/protected/`, `sql/roles/`, `scripts/backup/`.
Rujukan kode: paket buku Onno W. Purbo (`compose.yaml`, `toolkit/crypto_codec.py`,
`toolkit/blind_index.py`, `toolkit/openbao_client.py`, `toolkit/migrate.py`, `scripts/*.sh`).
Jika paket itu ada di `docs/reference/onno-code/`, baca dan ADAPTASI; jangan salin buta. Kekurangan
yang wajib diperbaiki: OpenBao client memakai `context` bukan AAD dan token statis; backup.sh
meninggalkan file plaintext; quick-start TLS dimatikan.

## Tahap 1 (prioritas tertinggi): infra
1. `infra/compose.yaml`: PostgreSQL 18 (boleh memakai container `pg-dpr` yang ada di port 5433, atau
   service baru) dan OpenBao (image dipin versi). OpenBao dengan TLS (sertifikat self-signed dari CA
   lokal yang dibuat skrip `infra/tls/make-ca.ps1` atau `.py`; private key tidak di-commit).
2. `infra/openbao/init.py` (atau .ps1): init + unseal manual (unseal key dan root token ditulis ke
   folder di LUAR repo yang ditentukan env `DPR_SECRETS_DIR`, dengan peringatan), enable Transit,
   buat kunci `pii-kek`, `finance-kek`, `search-hmac`, dan policy `svc-app`, `svc-migration`,
   `svc-verify`, `key-operator` sesuai kontrak. Terbitkan token per policy (TTL terbatas). AppRole
   opsional bila waktu cukup.
3. Cek dukungan `associated_data` di Transit OpenBao versi yang dipakai. Catat hasilnya di NOTES.md.
   Desain utama kita tidak bergantung pada itu (AEAD field dilakukan lokal dengan DEK per record).

## Tahap 2: toolkit kripto (`toolkit/`, paket Python `dprcrypto`)
1. `codec.py`: encrypt/decrypt blob v1 (AES-256-GCM, nonce acak 12 byte, AAD sesuai kontrak).
   Dekripsi gagal -> exception khusus, tanpa fallback.
2. `keys.py`: buat DEK per record (32 byte CSPRNG atau `datakey/wrapped`), wrap/unwrap via OpenBao
   Transit (`pii-kek`, `finance-kek`), dukung batch unwrap (Transit `batch_input`) untuk halaman daftar,
   cache DEK di memori dengan TTL pendek dan batas ukuran, DEK tidak pernah ditulis ke disk/log.
3. `bidx.py`: blind index sesuai kontrak (via `transit/hmac/search-hmac` atau HMAC lokal dengan
   kunci yang diambil dari OpenBao saat start; pilih satu, catat alasannya). Normalisasi per kolom
   sesuai kontrak.
4. `openbao.py`: client HTTP dengan TLS verify (CA dari env), token dari env, tanpa log token.
5. `masking.py`: format masking panitia (nama `On*** Pu***`, NIK 4 depan + 4 belakang, telepon
   `0812****7890`, email `on***@example.com`, rekening `************4567`).
6. `docs/contracts/test_vectors.json` + test yang memverifikasi vector. Test: round-trip, tamper
   1 bit gagal, swap antar-record gagal (AAD), swap antar-kolom gagal, nonce selalu berbeda.

## Tahap 3: policy dan skema
1. `policy/protection_profile.yaml`: dibangun dari `results/scanner/.../inventory.csv` + keputusan
   di kontrak bagian 3. Skrip `policy/build_profile.py` yang membaca inventory scanner, menerapkan
   override keputusan tim (file `policy/overrides.yaml`), dan menulis profile. Profile memuat per
   kolom: domain, aead, bidx, normalisasi, proyeksi analis, alasan. Ini bukti "Assessment-Driven
   Protection Profile".
2. `sql/protected/01_schema.sql`: skema `anggota_protected` sesuai kontrak (semua kolom `_ct`),
   `analyst_view` (hanya REF + age_band), tabel `audit_log`, tabel aplikasi `app_users`
   (username, password_hash Argon2id, role) bila Service App butuh di DB yang sama (koordinasi B).
3. `sql/roles/01_roles.sql`: semua role di kontrak bagian 10 dengan GRANT minimum. Password role
   diisi lewat variabel psql, bukan literal. `ALTER DEFAULT PRIVILEGES` dan REVOKE CREATE ON SCHEMA
   public FROM PUBLIC. `app_user` NOBYPASSRLS.
4. RLS (defense-in-depth): tabel `access_scope(principal, anggota_id, permission)` berlabel data
   kebijakan sintetis; policy RLS pada `anggota_protected` memakai `current_setting('app.principal', true)`
   yang di-set per transaksi (`SET LOCAL`). Catat keterbatasan: pencuri kredensial app_user bisa
   mengubah setting tersebut.

## Tahap 4: migrasi (`migration/`)
`python -m migration run --source baseline_100k --target protected_100k --profile policy/protection_profile.yaml`
1. Target database BARU (fresh). Terapkan skema + role.
2. Batch (mis. 1000 baris), idempoten (berdasarkan legacy_row_id), dapat dilanjutkan, dengan tabel
   kontrol progres.
3. Per baris: anggota_id UUIDv4, DEK_PII + DEK_FIN baru, wrap via OpenBao, enkripsi setiap kolom
   sesuai profile dengan AAD, hitung bidx, hitung age_band, tulis.
4. Validasi: decrypt-and-compare di memori untuk setiap baris (atau sampel besar + seluruh untuk 734),
   jumlah baris, jumlah NULL per kolom sama, keunikan bidx untuk kolom unik. Tanpa mencetak plaintext.
   Hasil ke `evidence/migration/validation.json`.
5. Mode `--source postgres --target protected_734` untuk data asli demo.
6. Setelah selesai: skrip pencabutan token `svc-migration`.

## Tahap 5: backup dan restore (`scripts/backup/`)
1. `backup`: `pg_dump -Fc` (role backup_user) di-stream langsung ke enkripsi (age atau AES-GCM
   dengan kunci backup terpisah dari domain data), TANPA file plaintext sementara. Tulis manifest:
   artifact id, waktu, sha256 artefak terenkripsi, ukuran, jumlah baris sumber, retention deadline.
   Manifest di-HMAC dengan kunci terpisah. Password/kunci tidak lewat argumen command line.
2. `restore`: verifikasi HMAC manifest + sha256, stream decrypt -> `pg_restore` ke database baru,
   validasi jumlah baris, smoke test dekripsi sampel (jika diberi akses kunci). Dua mode:
   tanpa OpenBao (data tetap ciphertext) dan dengan OpenBao (layanan pulih). Hasil ke
   `evidence/backup/restore-report.json`.
3. `tamper-test`: ubah 1 byte artefak -> restore harus menolak. Hasil ke `evidence/backup/tamper.json`.
4. `retention-test`: hapus 1 anggota sintetis -> backup baru -> restore -> pastikan anggota tidak ada.
   Hasil ke `evidence/backup/retention.json`.
5. Ukur waktu backup/restore dan ukuran artefak (dipakai benchmark).

## Tahap 6: rotasi kunci (jika tahap 1-5 hijau)
`rotate`: rotate `pii-kek` di OpenBao, rewrap semua `dek_pii_wrapped`, buktikan data tetap terbaca
dan versi berubah. Evidence ke `evidence/keys/rotation.json`.

## Definisi selesai minimum (Selasa malam)
Tahap 1-4 berjalan untuk `protected_734` dan `protected_100k`, test kripto lulus, test vector ada.
Tahap 5 selesai Rabu siang.
