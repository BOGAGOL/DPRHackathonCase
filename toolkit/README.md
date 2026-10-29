# dprcrypto — Tahap 2

Python 3.11+, kontrak `docs/contracts/CONTRACT.md` v1. Jalankan dari root repo:

```powershell
.\.venv\Scripts\python.exe -m pip install -e './toolkit[test]'
.\.venv\Scripts\python.exe -m pytest toolkit/tests -q
.\.venv\Scripts\python.exe -m dprcrypto.vectors verify
```

Untuk aplikasi/deployment: `python -m pip install ./toolkit` atau build wheel
`python -m pip wheel --no-deps ./toolkit --wheel-dir toolkit/dist`.
Paket runtime tidak bergantung pada `infra/`, aplikasi lama, atau direktori repo.

## Konfigurasi workload

Gunakan `infra/README.md` untuk bootstrap manual OpenBao TLS dan penerbitan token.
Client memerlukan tiga env var (tidak membaca recovery file atau `.env` sendiri):

- `OPENBAO_ADDR`: origin HTTPS, misalnya `https://127.0.0.1:8200`.
- `OPENBAO_CACERT`: path ke CA yang menandatangani sertifikat server.
- `OPENBAO_TOKEN`: token workload berumur terbatas dari policy yang sesuai.

`OpenBaoClient(token_env='NAMA_ENV')` mendukung nama env token terpisah untuk
proses/identitas yang berbeda. Nilai token diambil ulang dari env setiap operasi,
tanpa token literal di konstruktor. Identitas diperiksa lewat lookup-self, menolak
root/default/multiple policy dan token tanpa expiry terbatas. Client tidak
memperpanjang token; operator/secret agent menerbitkan pengganti sebelum expiry.
TLS memverifikasi CA dan hostname, minimum TLS 1.2, proxy env dan redirect dimatikan.

## Enkripsi record dan pencarian

Contoh berikut tidak mencetak nilai atau DEK. Kredensial disediakan melalui env
sesi oleh pengelola rahasia. UUID baru selalu UUIDv4, key baru terpisah per domain.

```python
from uuid import uuid4
from dprcrypto import BlindIndexer, KeyManager, OpenBaoClient, decrypt, encrypt

anggota_id = uuid4()
with OpenBaoClient() as bao, KeyManager(bao) as keys:
    record = keys.create_record_keys()
    protected = {
        'anggota_id': anggota_id,
        'protection_version': 1,
        'dek_pii_wrapped': record.pii.wrapped,
        'dek_fin_wrapped': record.finance.wrapped,
        'nama_ct': encrypt('Anggota Uji', record.pii.dek,
                           column='nama', anggota_id=anggota_id),
        'rekening_ct': encrypt('0000111122223333', record.finance.dek,
                               column='rekening', anggota_id=anggota_id),
        'email_bidx': BlindIndexer(bao).digest('email', 'uji@example.test'),
    }
    # Tulis hanya wrapped DEK, ciphertext bytes, dan bidx bytes ke database.
    # DEK dan hasil decrypt hanya digunakan dalam memori oleh endpoint berwenang.
```

API field: `encrypt(value, dek, *, column, anggota_id, protection_version=1)`
menghasilkan `bytes | None`. `decrypt(blob, dek, *, ...)` menghasilkan `str | None`.
`None` tetap NULL; string kosong tetap ciphertext terautentikasi. Pemanggil
menyerialisasi tanggal ke ISO YYYY-MM-DD dan angka ke string desimal. Codec tidak
mengubah tipe/normalisasi isi field. AAD dibentuk internal, bukan input bebas.
UUID string dinormalisasi ke canonical lowercase; identitas non-v4 ditolak.

`DecryptionError` menandakan format, tag, key, AAD, atau UTF-8 gagal. Pemanggil
harus mengembalikan error generik dan audit tanpa nilai; tidak boleh fallback.
`OpenBaoError` menandakan kegagalan transport/auth/response key service.

## Daftar: unwrap satu halaman per domain

Otorisasi object dan field dilakukan aplikasi **sebelum** memilih field untuk
unwrap/decrypt. Jangan unwrap domain FIN pada endpoint tanpa hak finance.

```python
with OpenBaoClient() as bao, KeyManager(bao, cache_ttl=15, max_entries=256) as keys:
    # rows sudah dipilih dengan otorisasi pengguna; tidak memuat plaintext DEK.
    deks = keys.unwrap_many('pii-kek', [row.dek_pii_wrapped for row in rows])
    names = [decrypt(row.nama_ct, dek, column='nama', anggota_id=row.anggota_id,
                     protection_version=row.protection_version)
             for row, dek in zip(rows, deks)]
    # Bentuk DTO sesuai peran; jangan log names/deks.
```

Batch mempertahankan urutan, menghapus request duplikat, dan memecah maksimum
100 item per request. Satu halaman 50 record memerlukan satu batch per domain.
Kegagalan satu item/chunk menolak seluruh hasil dan membersihkan cache manager.
Scope cache mencakup client/token dan KEK + wrapped DEK; pergantian token tidak
dapat mengambil key dari cache token sebelumnya.

Default cache TTL 15 detik, maksimum 60 detik; default 256 entri, maksimum 4096.
TTL tidak diperpanjang saat hit dan tidak melampaui expiry token. TTL=0 atau
max_entries=0 mematikan cache. `clear()` untuk revokasi/insiden; `close()` atau
context manager mengosongkan cache. Client harus ditutup terpisah bila dipakai
tanpa context manager.
TTL membatasi penggunaan key; pembuangan entri expired dilakukan secara lazy
pada operasi berikutnya, clear, atau close, tanpa background thread.

**Batas operasional:** revokasi server belum terdeteksi pada cache hit sampai
TTL habis atau proses menerima sinyal dan memanggil clear(). Token expiry lokal
tetap diperiksa pada hit. Cache hit dapat bekerja selama outage dalam lease itu;
uncached unwrap gagal. Bytearray cache ditimpa saat eviction/clear, tetapi Python,
library kripto, dan caller dapat memiliki salinan immutable: ini bukan jaminan
zeroization memori. Tidak ada persistensi DEK/token ke file atau log oleh toolkit.

## Blind index dan masking

`BlindIndexer(bao, key_version=1).digest(column, value)` mengembalikan 32 byte
HMAC atau None. Hanya no_ktp/email/pengguna. HMAC dihitung di OpenBao; search key
tidak diekspor. Label tepat `bidx|v1|<kolom>|<normalized>`, SHA-256.

- no_ktp: hanya ASCII 0–9, nol awal dipertahankan.
- email: strip + lower seluruh string, tanpa casefold/NFKC.
- pengguna: strip, case-sensitive.

Versi HMAC **dipin**, tidak memakai latest. Rotasi key OpenBao tidak otomatis
mengubah bidx lama. Perubahan versi index perlu migrasi/rebuild index bersama
semua penulis dan pembaca; bukan sekadar menaikkan konfigurasi satu service.

`mask_name`, `mask_nik`, `mask_phone`, `mask_email`, `mask_account` menghasilkan
contoh panitia dan menutup identifier pendek. Masking adalah proyeksi tampilan;
bukan pengganti otorisasi. Jangan kirim plaintext tambahan ke browser.

## Test vector dan integrasi

`docs/contracts/test_vectors.json` adalah fixture **PUBLIC TEST ONLY** sesuai
pengecualian eksplisit kontrak bagian 9: DEK/search key sintetis, AAD, nonce,
blob, bidx. Key fixture tidak boleh digunakan untuk data aplikasi. Nonce tetap
di fixture hanya untuk reproduksi lintas bahasa; API encrypt selalu CSPRNG.
Verifier menulis hanya status/checks ke `evidence/crypto/vectors.json`.

```powershell
$env:DPR_CRYPTO_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m pytest toolkit/tests -q --tb=short --junitxml=evidence/crypto/toolkit-tests.xml
Remove-Item Env:DPR_CRYPTO_INTEGRATION
```

Uji memakai project/volume Docker acak, CA dan bootstrap material di luar repo,
tanpa database, dan membersihkan hanya resource miliknya. Hasil mesin ke
`evidence/crypto/integration.json`. Test penuh repo yang relevan:

```powershell
$env:DPR_INFRA_INTEGRATION = '1'
$env:DPR_CRYPTO_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m pytest tests infra/tests toolkit/tests -q --tb=short
Remove-Item Env:DPR_INFRA_INTEGRATION, Env:DPR_CRYPTO_INTEGRATION
```

Modul B perlu mengimpor paket ini atau lulus vector di backend bahasa lain.
Prototipe `apps/api/app/crypto.py` sudah dihapus dari snapshot aktif; formatnya tidak kompatibel dan
tidak diubah oleh Tahap 2. Migrasi/penggantian adaptor aplikasi dilakukan pemilik
Modul B; jangan mencampur envelope JSON lama dengan bytea blob v1.
