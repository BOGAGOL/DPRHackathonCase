# Rilis dependency aplikasi — 29 Oktober 2026

Upgrade Modul A `a8adeb6` digabung dengan main `74f6205`, ditambah pytest 9.0.3
di requirements first-party dan batas cryptography `>=50.0.2,<51` pada app.
Merge main yang dipush: `4fdd7aa5a87e553f8da1e1397d5d5a772c80a402`.
Review advisory asal: [CRYPTOGRAPHY_20261029.md](CRYPTOGRAPHY_20261029.md).
Keterangan prototipe lama dalam review asal merupakan kondisi saat review;
deklarasi `apps/api` juga diselaraskan oleh rilis ini. Prototipe tersebut tidak
termasuk backend aplikasi yang diuji. Referensi buku historis tidak diubah.

## Verifikasi lokal sebelum merge

- Venv baru: Python 3.12.10, cryptography 50.0.2, pytest 9.0.3, pip check lulus.
- Toolkit: 108 passed, 1 skipped; app: 437 passed, 1 skipped.
- Verifier shared vectors: 8 pemeriksaan lulus. Vectors tidak diregenerasi.
- Skip merupakan integrasi opt-in; hasil ini tidak menggantikan pentest.

Hasil mesin dan JUnit berada di `app/evidence/access-control/dependency-upgrade-*`.
Environment lama dan checkout pengguna tidak diganti oleh proses pengujian lokal.

## Deployment VM nyata

VM `43.156.157.247`, `/home/ubuntu/juara1onno`, dikonfirmasi **bukan Git checkout**.
Karena itu git pull tidak dijalankan. Paket berasal dari git archive merge main
dan manifest SHA-256 memverifikasi 159 file source runtime/dependency. Source
backend/scripts, toolkit, infra, migration, contracts, policy dan SQL source
diselaraskan; SQL tidak diterapkan, frontend build dan konfigurasi privat tetap.
`commit_after` di laporan berarti identitas manifest rilis subset source, bukan
hasil `git rev-parse HEAD` atau klaim seluruh frontend memakai commit tersebut.
Commit awal tidak diketahui dan dicatat null; hash backup subset source tersedia.

Operator Zhafif mengunggah dan menjalankan paket lewat sesi SSH sendiri. Backup
source yang ditimpa dan salinan venv persis dibuat privat sebelum perubahan.
Smoke awal wajib lulus sebelum dua service aplikasi dihentikan dan dependency
dipasang. Skrip menyediakan pemulihan source/venv dan smoke setelah pemulihan
jika upgrade gagal. Pada deployment ini rollback tidak diperlukan, sehingga
jalur rollback dependency tidak diuji secara nyata.

| Pemeriksaan | Hasil VM |
|---|---|
| Selesai, WIB | 2026-10-29 11:41:01 +07:00 |
| cryptography | 46.0.7 → 50.0.2 |
| pytest | 9.0.2 → 9.0.3 |
| pip check | PASSED |
| dpr-api.service / dpr-web.service | active / active |
| Smoke sebelum upgrade | 65/65, 14 akun |
| Smoke setelah upgrade | 65/65, 14 akun |

Laporan asli dari VM:

- `app/evidence/access-control/vm-dependency-upgrade-20261029.json`
- `app/evidence/access-control/vm-pentest-smoke.json`
- `app/evidence/access-control/dependency-upgrade-release-20261029.json`

Hanya dua service aplikasi dihentikan/dijalankan kembali. PostgreSQL dan OpenBao
tidak direstart; tidak ada provisioning/rotasi akun, reset database, rotasi kunci,
reboot, atau perubahan layanan Ardi. Login/logout smoke menghasilkan sesi dan
audit normal; tidak menjalankan PATCH/POST data anggota. VM siap diserahkan ke
pentest Delf setelah upgrade. Ini bukan pernyataan hasil pentest atau kesiapan
produksi. Masa berlaku token OpenBao tetap mengikuti kebijakan existing.

SBOM/audit terbaru dan batas cakupannya: [../sbom/README.md](../sbom/README.md).
