# Integrasi B → toolkit A (28 Oktober 2026)

Implementasi A sudah tersedia di main b8e9998. Adapter B memakai API publik aktual,
bukan meminta A menambah factory. Default `DPR_CRYPTO_FACTORY=dprcrypto:public-v1`.
Nama lama `dprcrypto:create_service` diterima sebagai alias konfigurasi ke adapter yang sama;
tidak ada import factory dinamis. Python minimal 3.11, pengujian memakai 3.12.10.

| Operasi internal B | API toolkit A |
|---|---|
| koneksi | `OpenBaoClient()` membaca environment dan memverifikasi TLS/identitas workload |
| blind_index | `BlindIndexer(client, key_version=1).digest(column, value)` |
| unwrap_many | `KeyManager(client, cache_ttl=0, max_entries=0).unwrap_many(kek, wrapped)` |
| decrypt/encrypt field | `dprcrypto.decrypt` / `dprcrypto.encrypt` |
| new_record_keys | `KeyManager.create_record_keys()`; pasangan `.pii` dan `.finance` |

Domain `pii` dipetakan ke `pii-kek`, `fin` ke `finance-kek`. Normalisasi, AES-GCM,
HMAC, AAD, nonce dan pembungkusan DEK sepenuhnya dikerjakan toolkit A.
AAD memakai UUID internal anggota, nama field sumber dan protection_version.
Locator API tetap legacy_row_id; locator tersebut tidak dipakai sebagai AAD.
NULL tetap NULL. Tidak ada salinan plaintext tambahan atau fallback lokal.

DEK tidak dicache antarpanggilan: pencabutan token berlaku pada operasi berikutnya,
dengan biaya unwrap tambahan. Daftar tetap batch unwrap satu halaman dan hanya
mendekripsi nama. Detail/PATCH hanya meminta field dan domain yang diizinkan.
Kegagalan toolkit menghasilkan HTTP 500 generik dan audit metadata tanpa nilai data.

Bukti nyata: `app/evidence/access-control/protected-integration.json` memakai schema A,
PostgreSQL 18 dan OpenBao TLS sementara; mencakup ciphertext buatan A dibaca B,
update bidx, AAD swap, pencabutan token dan browser HTTPS enam peran.
`crypto-vectors.json` berasal dari CLI verifier A terhadap vectors bersama.
Test double pada suite SQLite hanya untuk policy, bukan bukti kriptografi.

Reproduksi dari root repo, setelah instalasi dependensi README:

```powershell
app/.venv/Scripts/python -m dprcrypto.vectors verify --evidence app/evidence/access-control/crypto-vectors.json
app/.venv/Scripts/python app/scripts/protected_probe.py
```

Probe memakai fixture sintetis kecil dan resource Docker acak miliknya sendiri.
Kelulusannya tidak membuktikan migrasi protected_734/100k/1m atau benchmark performa.
Setup akun, scope, audit dan RLS dijelaskan di [INTEGRATION_A.md](INTEGRATION_A.md).
