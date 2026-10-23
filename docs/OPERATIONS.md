# Instalasi, migrasi dan pemulihan

Gunakan dataset sintetis yang diberikan panitia secara lokal. Repo tidak mendistribusikan dump sumber. Semua perintah dijalankan dari root `web_user/juara1onno`.

1. Instal Python 3.10+ (image Docker memakai 3.12), Node.js 24 LTS, PostgreSQL 17 dan client tools di PATH, atau Docker Desktop dengan Linux Engine aktif. Dependensi Python dipin di requirements; frontend memakai package-lock. Environment implementasi: Windows, Python 3.10.11, Node 24.15.0, PostgreSQL 17.4.
2. Buat virtualenv dan instal requirements sesuai README. Generate `.env`; simpan salinan recovery terenkripsi di lokasi berbeda dari dump. Di Windows, `chmod` Python tidak menggantikan ACL NTFS: batasi folder proyek/secret ke akun tim yang perlu.
3. Jalankan dua cluster lab lokal atau dua container. Gunakan satu jalur agar port 55432/55433 tidak bentrok. Jangan menghapus volume atau memindahkan server asli.
4. Jalankan Alembic dengan migration owner, lalu grants runtime, import dan provisioning. Seluruh migrasi data protected berada dalam satu transaksi; baseline yang sudah identik diterima. Sumber yang berbeda atau protected non-empty tanpa import manifest yang cocok ditolak. Rerun setelah edit bisnis sengaja gagal verifikasi kesamaan sumber; jangan mengimpor ulang untuk menimpa perubahan sah.
5. `verify` melakukan kesamaan seluruh 29 nilai, count dan blind index. Parser mandiri juga dibandingkan dengan scanner referensi dalam verifikasi keamanan offline. Tidak mengubah format KTP/email sumber yang tidak sesuai validasi form.
6. Simpan `.local/demo-accounts.json` privat. Password tidak pernah dicetak oleh provisioning. Akun baru minimum 12 karakter. Untuk mengganti akses, admin memasukkan daftar permission dan assignment pengganti; sesi target dicabut. Role tidak berubah melalui endpoint akses.

Backup dan restore:

```powershell
.venv/Scripts/python scripts/backup.py drill
```

`pg_dump --format=custom --no-owner --no-acl` masuk memori dan dienkripsi AES-256-GCM dengan kunci backup independen. Tidak ada file dump plaintext. Secret koneksi dikirim melalui environment child process, bukan argumen. `.local/protected.backup.enc` menggantikan backup hanya setelah enkripsi berhasil. Kunci `.local/backup-recovery.key` wajib dipindahkan/disalin ke penyimpanan recovery terpisah; file lokal bersama ciphertext hanyalah kemudahan lab, bukan pemisahan kustodi produksi. Backup lama jangan ditimpa sebelum kebijakan retensi ditetapkan.

Restore mendekripsi+memverifikasi tag sebelum menjalankan `pg_restore`, selalu membuat database baru `dpr_restore_<random>`. Database asli tidak ditimpa/dihapus. Drill memeriksa count dan mendekripsi seluruh field hasil restore. Backup tidak mengandung kunci field; pemulihan penuh memerlukan recovery key backup DAN key version field yang sesuai. Database hasil drill dipertahankan untuk pemeriksaan; hapus secara eksplisit dengan tool DBA setelah tim menyetujuinya. Restore bukan publikasi otomatis atau cutover.

Rollback: hentikan mutasi; buat backup current; pulihkan backup pra-migrasi pada instance baru; verifikasi count, logical equality dan kontrol akses; bandingkan delta perubahan sah; ubah konfigurasi setelah verifikasi. Jangan mengganti protected website dengan baseline plaintext. Alembic downgrade awal sengaja menolak penghapusan tabel. Script tidak menghapus atau mengubah SQL sumber.

Rotasi lokal: backup terlebih dahulu; tambahkan versi baru AES 32 byte acak ke `ENCRYPTION_KEYS` sambil mempertahankan versi lama, ubah `ENCRYPTION_KEY_VERSION`, hentikan mutasi layanan, jalankan `scripts/manage.py rekey`. Semua envelope baru ditulis atomik setelah berhasil didekripsi. Verifikasi data dan recovery, restart layanan. Jangan menghapus kunci lama selama backup lama membutuhkannya. HMAC key rotation membutuhkan kolom/index paralel + reindex semua identifier dan cutover; belum diotomasi. Jangan mengganti HMAC key begitu saja.

OpenBao target: provision key `aes256-gcm96` dengan pengelola kunci; berikan app policy encrypt/decrypt di `infrastructure/openbao-app-policy.hcl`. Aktifkan TLS dan sertifikat yang dipercaya host/container, gunakan token terbatas berumur pendek. `CRYPTO_PROVIDER=openbao`, `OPENBAO_URL=https://...`, `OPENBAO_TOKEN` injected secret. Adapter tidak mengekspor key, memverifikasi TLS, mengirim AAD. Transit version ditentukan ciphertext `vault:vN`, envelope version=1 adalah versi format. Kegagalan Transit menghasilkan 503 untuk detail yang membutuhkan dekripsi; list publik dapat tetap tersedia. Migrasi envelope lokal ke Transit memerlukan tool dual-provider terotorisasi, belum diimplementasikan; memilih provider baru pada data lama akan gagal tertutup.

Deployment HTTPS: pasang reverse proxy dengan sertifikat valid (contoh Caddyfile), set `APP_ORIGIN=https://domain`, `COOKIE_SECURE=true`, konfigurasi TLS PostgreSQL `sslmode=verify-full` dengan root CA. Gunakan volume/host encryption untuk file DB/WAL dan secret store, bukan `.env` lab. Compose yang disediakan adalah profil development; jangan menganggapnya deployment TLS. Periksa jalur proxy ke API serta PostgreSQL dan Transit, bukan browser saja. CORS sengaja tidak dibuka; browser selalu memakai origin Next.js.

Retensi usulan: session maksimum 30 menit dan hapus session expired melalui job DBA; audit sesuai kebijakan instansi, usulan lab 30 hari; backup lab usulan 7 hari setelah demonstrasi. Angka ini rancangan, bukan ketentuan DPR. Belum ada job penghapusan/retensi otomatis atau uji data terhapus dari backup baru. Hapus berdasarkan identifikasi dataset/backup, pertahankan bukti penghapusan, jangan menghapus key yang masih dibutuhkan backup sah.

Insiden: cabut session/identity Transit yang terdampak, hentikan mutasi, amankan bukti audit tanpa menambah PII, rotasi credential terkait, lakukan assessment akses dekripsi dan re-encryption yang sesuai. Kebocoran aplikasi sekaligus akses dekripsi dapat membuka data; kriptografi tidak meniadakan skenario ini.
