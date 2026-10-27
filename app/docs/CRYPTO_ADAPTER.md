# Titik integrasi B → A

Ini interface aplikasi, bukan perubahan CONTRACT.md atau implementasi kriptografi baru. Seluruh format AEAD/AAD, normalisasi HMAC, pembuatan dan pembungkusan DEK tetap milik `toolkit/dprcrypto`. Factory belum dapat diuji terhadap paket A yang belum tersedia. Mode plain tidak mengimpor atau memerlukan paket ini.

Factory default `dprcrypto:create_service` dapat diganti melalui `DPR_CRYPTO_FACTORY=dprcrypto.<module>:<factory>` agar cocok dengan entrypoint A. Namespace selain `dprcrypto` ditolak. Factory dipanggil dengan `openbao_addr`, `token`, `ssl_context`; context memverifikasi CA eksplisit. Driver mengimplementasikan:

```python
blind_index(column: str, value: str) -> bytes  # 32-byte contract HMAC
unwrap_many(domain: str, wrapped: list[str]) -> list[bytes]  # same input order, 32-byte DEKs
decrypt_field(blob: bytes, dek: bytes, *, anggota_id: str,
              column: str, protection_version: int) -> str
encrypt_field(value: str, dek: bytes, *, anggota_id: str,
              column: str, protection_version: int) -> bytes
new_record_keys() -> dict  # {"pii": (dek_bytes, wrapped_str), "fin": (dek_bytes, wrapped_str)}
```

Driver A wajib menggunakan AAD persis kontrak dengan UUID internal lowercase, nama kolom sumber tanpa suffix `_ct`, dan protection_version. Wrapped DEK hanya metadata DB; DEK plaintext tidak pernah dicetak, ditulis ke file, dikirim ke browser, atau dimasukkan evidence. `None` ditangani sebagai SQL NULL, bukan string kosong.

Repository B membatasi SQL projection terlebih dahulu. Daftar mengambil `nama_ct`, UUID/versi dan `dek_pii_wrapped` saja, lalu satu batch unwrap untuk halaman 50 record. Tidak mengambil DEK FIN untuk daftar. Detail finance saja yang meminta DEK FIN. PATCH mengambil hanya metadata yang diperlukan untuk mengenkripsi perubahan, mengunci row, memperbarui ciphertext dan `email_bidx` dalam transaksi sama. Insert menyiapkan dua domain melalui driver A. Tidak menambahkan fallback enkripsi lokal.

Driver test dalam `app/tests` hanya menyimpan opaque references acak di memori untuk menguji policy dan pemanggilan adapter. Itu **bukan enkripsi** dan tidak dapat diaktifkan melalui environment runtime; injeksi driver hanya diterima Settings.testing yang tidak diekspos oleh CLI. Bukti parity dan swap dari test double bukan bukti format ciphertext nyata. Shared test vectors dan live OpenBao wajib diuji lagi setelah paket A tersedia.

Jika format factory A berbeda, sesuaikan bridge pada `app/backend/service_app/crypto.py` sambil tetap memanggil primitive A. Jangan menulis AES/HMAC/OpenBao client kedua. Kegagalan adapter/dekripsi menjadi HTTP 500 generik dan audit metadata, tidak mengirim exception atau plaintext. Jangan mengubah `toolkit/` atau kontrak dari branch Modul B.
