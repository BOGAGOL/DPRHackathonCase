# Otomatisasi token Service App (Modul B)

Token aplikasi tetap dibatasi maksimal empat jam. Timer memeriksa setiap lima menit,
dan memperoleh token baru ketika sisa TTL <= satu jam. Identitas AppRole khusus
`auth/dpr-service-app/role/service-app` hanya menghasilkan policy `svc-app` tanpa
default policy. Tidak menambah izin policy Transit, mengubah ciphertext/kunci,
database, akun, atau komponen Modul A/C. Format kontrak v1 tetap sama.

## Pemasangan satu kali pada VM Ubuntu existing

Kode VM dipasang lewat arsip, bukan `git pull`. Dari PowerShell, buat paket dengan
`python app/scripts/build_token_refresh_release.py`. Upload arsip yang dilaporkan ke
`ubuntu@43.156.157.247:/home/ubuntu/dpr-token-autorefresh.tar`. Di SSH sebagai ubuntu:

```bash
cd /home/ubuntu
tar -xf dpr-token-autorefresh.tar
bash /home/ubuntu/dpr-token-autorefresh/apply.sh
```

Periksa SHA256 arsip terhadap hasil builder sebelum extract. Installer memverifikasi
delapan checksum payload dan dua launcher existing sebelum mengganti kode. Perubahan
orang lain ditolak. Backup launcher disimpan privat di
`~/dpr-demo-zhafif/private/service-b/token-autorefresh-backup/`.

Setup satu kali memakai bootstrap privat yang sudah dimiliki operator untuk membuat
mount AppRole terpisah. Ia tidak menulis ulang policy/key/mount Transit, melakukan
init/unseal, atau restart PostgreSQL/OpenBao. Runtime timer **tidak dapat membaca**
material bootstrap, kredensial database operator, atau akun privat.

Hasil penerapan: `app/evidence/access-control/vm-token-autorefresh.json` dan
`token-autorefresh-smoke.json`. Smoke existing menjalankan 65 pemeriksaan pada 14 akun
tanpa provisioning atau perubahan data anggota. Ini bukan pengujian durasi empat jam
dan bukan pengganti hasil pentest.

## Cara kerja dan lokasi rahasia

- Program broker: `/usr/local/lib/dpr-service-app/token_refresh.py`, root-owned,
  stdlib Python sistem; tidak menjalankan venv/code milik ubuntu sebagai root.
- Credential AppRole: `/etc/dpr-service-app/auto-token.json`, root:root 0600,
  directory 0700. Root token/unseal share tidak disimpan di sini.
- Sink: `/run/dpr-service-app/svc-app.token`, root:ubuntu 0640, directory 0750.
  API hanya memperoleh token `svc-app`, bukan SecretID atau bootstrap.
- State metadata: `/run/dpr-service-app/state.json`, root-only, tanpa token.
- API drop-in: `/etc/systemd/system/dpr-api.service.d/token-auto.conf`.
- Timer: `dpr-token-refresh.timer`; oneshot: `dpr-token-refresh.service`.

Setiap token baru diverifikasi menggunakan `lookup-self`: hanya svc-app, tanpa identity
policy tambahan, TTL/explicit_max_ttl <= 14400. HTTPS/CA diperiksa tanpa proxy environment
atau redirect. Penulisan sink atomik. Backend membaca sink pada startup; mengganti
file saja tidak cukup. Broker restart **hanya dpr-api** lalu memeriksa readiness TLS.
Sesi pengguna tetap di database; web tidak direstart. Ada jeda singkat saat restart API.
Token lama dicabut setelah reload/readiness berhasil, atau tetap dibatasi TTL bila
pencabutan tidak tersedia. Kegagalan reload dicoba kembali pada tick berikutnya tanpa
terus menerbitkan token baru. API yang sengaja inactive saat maintenance tidak dinyalakan.

Tidak ada cron yang berulang kali memakai bootstrap/root token. Sebagai gantinya,
SecretID AppRole memakai TTL/usage tak terbatas untuk unattended login. Ini adalah
**kredensial jangka panjang** yang wajib dilindungi dan dicabut saat akses host dicabut.
Pencurian SecretID+RoleID dapat menghasilkan token svc-app baru sampai role/SecretID
dicabut. Root host tetap di luar perlindungan ini. Migrasi ke workload identity yang
tidak memerlukan credential statis merupakan pengembangan berikutnya.

Jika OpenBao sealed, jaringan/TLS rusak, atau AppRole dicabut, operasi tetap fail
closed. Broker tidak otomatis unseal atau menghidupkan layanan kunci. Setelah reboot,
operator tetap harus unseal sesuai prosedur; timer kemudian dapat pulih otomatis.

## Pemeriksaan operator (tanpa menampilkan token)

```bash
systemctl is-active dpr-token-refresh.timer dpr-api.service dpr-web.service
systemctl list-timers dpr-token-refresh.timer --no-pager
sudo /usr/bin/python3 -I /usr/local/lib/dpr-service-app/token_refresh.py status
sudo journalctl -u dpr-token-refresh.service -n 10 --no-pager
```

`status` hanya metadata pemeriksaan terakhir, bukan lookup live. Jalankan
`sudo systemctl start dpr-token-refresh.service` untuk pemeriksaan baru. Token sehat
tidak diterbitkan ulang dan API tidak direstart pada setiap pemeriksaan.

Untuk berhenti menjadwalkan login baru: `sudo systemctl disable --now
dpr-token-refresh.timer`. Ini tidak mencabut credential AppRole atau memperpanjang
token berjalan. Untuk dekomisioning, operator Modul A perlu menghancurkan SecretID
melalui accessor dalam config privat atau menonaktifkan **hanya mount auth
dpr-service-app**. Jangan menghapus/menonaktifkan mount Transit atau kunci enkripsi.
Kembali ke token manual memerlukan handoff token valid, menghapus hanya drop-in
`token-auto.conf`, daemon-reload, dan restart API.

## Verifikasi

Tes sintetis: `python -m pytest app/deploy/tests app/tests` (temp di luar repo).
`app/deploy/tests/native_bao_check.py` hanya untuk container disposable berlabel tes:
OpenBao 2.5.5 HTTPS, AppRole nyata, empat jam max TTL, recovery setelah token ditolak,
revokasi, permission sink, CA salah, dan pemuatan sink. Callback systemd pada lab
disimulasikan; penerapan VM dan smoke dicatat terpisah, tidak dianggap lulus dari tes lokal.

Referensi API: https://openbao.org/docs/auth/approle/ dan
https://openbao.org/api-docs/auth/approle/ .
