# Dataset kondisi awal — hanya untuk repo PRIVATE

`02_data.sql` berisi dataset sintetis milik panitia. Berkas ini sengaja menyimpan
kondisi awal plaintext untuk reproduksi lab dan hanya boleh berada di repo **PRIVATE**.
Dilarang memublikasikan dataset, menyalinnya ke fixture/evidence publik, atau mengubah
repo menjadi public. Menghapus file dari working tree tidak menghapusnya dari riwayat Git.

Keputusan tim 27 Oktober 2026 mengizinkan commit path ini dan mengamendemen aturan lama
PROJECT_CONTEXT bagian 11; ketentuan mengikat dicatat di CONTRACT bagian 11.

- Keluarkan `sql/baseline/02_data.sql` dari paket lampiran publik. `.gitattributes`
  menetapkan `export-ignore`, sehingga `git archive` tidak menyertakannya. Pembuatan
  paket dengan alat lain wajib menerapkan pengecualian yang sama.
- Path persis ini dikecualikan dari scan plaintext S06 (`verify/scan_config.toml`)
  karena merupakan baseline plaintext, serta dari gitleaks (`.gitleaks.toml`).
  Ini bukan bukti bahwa log, evidence, atau sistem protected bebas kebocoran.
- Tidak ada pengecualian untuk password/token/kunci aktif atau file SQL lain.
  Snapshot plaintext hasil datagen dan known-values tetap di `DPR_PRIVATE_DIR` di luar repo.

`01_schema.sql` mendefinisikan schema dan `03_validasi.sql` menyediakan query pemeriksaan.
Jangan menjalankan DDL/DML atau restore terhadap database sumber `postgres` yang sudah ada.
