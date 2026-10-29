# Jalur reproduksi pengumpulan

- Launcher mengorkestrasi modul yang ada; format v1, ACL/RLS, target benchmark,
  dataset/evidence historis dan runtime deployment tidak diubah.
- `setup` membuat dua environment karena pin psycopg A/B dan C berbeda. `npm ci`
  dan build memakai lockfile aktif. Tidak membaca `.env` developer.
- `demo`/`verify` selalu membuat cluster dan key plane BARU dengan nama/port acak.
  Tidak menerima host/container/database existing sebagai target. Sumber `postgres`
  pada alur ini adalah DB baru milik invocation, bukan pg-dpr tim.
- Input 734 record diparse literal, tidak dieksekusi sebagai SQL bebas. Import tidak
  menjalankan DROP dari DDL baseline. Scanner memakai reader read-only; profile
  baru dibangun dari scan baru + override/kontrak yang sama, tanpa menimpa profile tim.
- Native PostgreSQL memakai opsi `psql_bin` eksplisit pada provisioning; script SQL,
  guard target/version/identity, password via environment dan transaksi tetap sama.
  Backup mempunyai transport native opt-in `DPR_BACKUP_NATIVE_PG_BIN`; allowlist
  program, verify-full dan binding sesi yang sama tetap diberlakukan. Default Docker
  unchanged. Tidak ada monkeypatch, mock crypto, SQLite atau API palsu di alur ini.
- Auto-init/unseal hanya untuk key plane baru milik demo ini. Ini bukan auto-unseal
  production. Material root+shares dibuat privat di luar checkout; operator production
  tetap wajib memisahkan custody dan unseal manual sebagaimana runbook VM.
- Password, DEK, token dan isi respons pribadi tidak dicetak. Enam kredensial demo
  acak hanya ada di folder privat; stdout berisi progress/count/path dan status.
- Chrome lokal menggunakan pin SPKI sertifikat ephemeral persis seperti acceptance
  sebelumnya; tidak mematikan validasi TLS global atau memasang CA OS diam-diam.
- Semua report baru di `evidence/reproduction/<run-id>/`. Gagal tetap dicatat FAIL,
  bukan mengganti evidence lama. Run ini bukan benchmark resmi atau DR key-plane.
- Ctrl+C menghentikan proses/project invocation. Native cluster/recovery material
  berhenti tetapi folder privat dipertahankan agar material tidak hilang diam-diam;
  operator boleh menghapus direktori run setelah tidak diperlukan. Tidak ada prune
  Docker global dan tidak ada penghapusan volume/container existing.

Hasil akhir: setup clone baru PASS; verify dan demo native 734 PASS (100 pemeriksaan
Chrome per run). Core394/10skip, B473/12skip, scanner/datagen218/1skip,
benchmark/verify155/1skip; targeted launcher/profile/packaging76 PASS (bertumpang
tindih, jangan dijumlahkan sebagai test unik). Docker runtime gagal engine500;
Compose syntax PASS. Lihat evidence/reproduction/final-verification.json.
