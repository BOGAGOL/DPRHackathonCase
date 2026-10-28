# Benchmark API read-path, laptop

Jalankan hanya atas instruksi operator. Tidak mengubah app/; backend HTTPS dari
app/scripts/serve.py, app_user verify-full di kedua mode, https_pool, DEK cache OFF.
Server deployment tidak disentuh. Install app dependencies di app/.venv dan toolkit
editable; k6 Windows user install yang terukur v1.2.3. Versi runtime disimpan setup.json.

Nama allowlist app dipenuhi dengan menukar nama dua database: original -> __official,
CREATE DATABASE memakai original sebagai template, setup/provisioning hanya pada copy.
Original dikunci ALLOW_CONNECTIONS=false sementara; flag, nama dan OID dipulihkan.
Journal atomic+fsync db_swap_state.json ditulis sebelum mutasi dan berstatus swapped
sebelum setup. DROP hanya jika OID cocok dengan copy yang dibuat sesi; original atau
OID tidak dikenal tidak pernah dihapus. Jangan menjalankan ulang sesi pada journal existing.

Seluruh tabel kontrol dan sequence official juga di-hash/count selain data anggota.
Finally: hentikan tree proses server Windows (bukan hanya venv launcher), terminasi
koneksi copy, drop copy, rename original, cek semua data/control/sequence dan koneksi
bench_user/scanner_user tanpa TLS pada kedua baseline. Status restored hanya sesudah
semua verifikasi lulus. Supervisor terpisah menangani worker exit mendadak;
restore_failed berhenti dan memerlukan operator, tanpa loop pemulihan otomatis.

Provisioning CLI B membuat enam demo account identik per mode; tepat satu
privileged_officer dipakai benchmark. Scope read protected diperluas admin copy
ke seluruh 100k agar total dan pagination sama dengan plain, mencakup korpus DB2048.
Password/file account dan korpus hanya di direktori privat dengan ACL operator.
Parity 200 key x4 endpoint x2 mode membandingkan seluruh body JSON, hanya header diabaikan.
Mismatch berisi nama field, tidak berisi nilai.

Dua blok B/P/P/B, empat endpoint GET, 8VU dan60s per run. App restart hanya saat mode
berubah; warmup30s sesudah tiap start. K6 login8x sebelum pengukuran setiap run.
Satu akun dibatasi10 login/300s oleh app, sehingga jeda login310s dilakukan di luar
window ukur. Estimasi2,5–3 jam; gate token minimum2jam ditambah anggaran sesi10400s
sebelum swap agar cukup untuk cooldown. Tidak auto-issue/renew/read root.

K6 tags URL/error-message dinonaktifkan, nama request diset label endpoint; body
respons dibuang. Custom latency hanya sampel terukur, blocked+duration. K6 logs
dinonaktifkan agar error transport tidak mencetak query NIK/email. Raw JSON gzip,
status HTTP, metadata, resource app/server PID asli, k6, PG dan OpenBao disimpan.
TLS k6 di Windows memakai CurrentUser/Root: launcher menambah lab CA sementara bila
belum dipercaya dan menghapus hanya certificate yang ditambahnya saat selesai.
Receipt CA dan log supervisor di results/bench/api_bppb_100k; tidak ada private key/token.

```powershell
# Menjalankan detached, stdout/stderr ke results/. Lakukan hanya satu kali.
.\benchmark\api\launch.ps1 -Action supervise -Detached
# Pemulihan eksplisit setelah operator memeriksa journal dan service sudah siap:
.\benchmark\api\launch.ps1 -Action recover
```

Jangan unseal/start container otomatis. AC putus menginvalidasi seluruh blok;
ulang blok setelah AC kembali. Crash app, OpenBao mati/sealed, atau identitas OID
tidak cocok menghentikan sesi dan masuk cleanup. Tidak menyentuh DB official lain.
Hasil API berdampingan dengan DB v2; TLS DB kedua mode, DTO, HTTP dan audit berbeda.
Benchmark ulang/hasil pada kode baru harus dipisahkan jika hash produksi berubah.
