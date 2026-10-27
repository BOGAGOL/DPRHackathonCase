# Pemeriksaan awal tahap 4 — 27 Oktober 2026

Sinkronisasi dengan main `20e08f3`: belum menjalankan migrasi atau menulis data
anggota ke protected_734/protected_100k. Tidak diperlukan dump tambahan untuk
clone development lokal: file 02_data.sql identik dengan main dan source 734
serta baseline 100k sudah tersedia. Verifikasi read-only kembali lulus untuk
checksum kedua sumber dan TLS seluruh DB (`evidence/development/verify.json`).
Bukti baseline awal DB C tersedia: 21 run dan 3 restore berhasil. Bukti itu
tidak menggantikan benchmark API/eksperimen B-P-P-B yang masih terpisah.

OpenBao lokal 2.5.5 terjangkau melalui verified TLS, tetapi initialized=false,
sealed=true pada pemeriksaan status. Init/unseal manual, konfigurasi Transit,
dan penerbitan token workload diperlukan sebelum migrasi nyata. Tidak ada root
token atau unseal share yang perlu dimasukkan ke repo. Material recovery berada
di DPR_SECRETS_DIR eksternal; service memakai env/token ber-TTL terbatas.
svc-migration tidak boleh decrypt; decrypt-and-compare harus menggunakan
identitas decrypt yang terpisah dan diizinkan, bukan memperluas policy migrasi.

Handoff Service App yang kini tersedia di main memerlukan sinkronisasi kode:

- B mengharapkan factory dprcrypto:create_service dan lima method adapter; A
  saat ini menyediakan primitive OpenBaoClient/KeyManager/BlindIndexer/codec.
- B memakai users/sessions dan bentuk audit_log yang berbeda dari app_users
  serta audit metadata tahap 3 A. Jangan menjalankan bootstrap B langsung pada
  skema protected A sebelum kedua bentuk diselaraskan.
- Principal protected B adalah hex blind index pengguna (binding bidx:v1:hex),
  sementara access_scope/request_principal A memakai UUID akun. Kedua identitas
  tidak dapat langsung dipertukarkan; jangan melemahkan RLS agar tes lolos.
- Locator HTTP B adalah legacy_row_id; migrasi mempertahankan ID sumber di situ.
  AAD tetap menggunakan UUIDv4 internal anggota_id, sesuai kontrak.

Ini pekerjaan integrasi kode, bukan kekurangan file yang harus disuplai pengguna.
Folder app/ tetap milik B; koordinasi perubahan tidak boleh mengubah format
kriptografi kontrak v1 secara sepihak. Rujukan B: app/docs/CRYPTO_ADAPTER.md,
app/docs/LOCAL_LAB.md, app/backend/service_app/models.py.
