# Review advisory cryptography — 29 Oktober 2026

Branch `fix/cryptography-security`, dari main `845ee93`. Ini review dependency dan
uji kompatibilitas lokal, bukan deployment, pentest, atau pengukuran benchmark baru.
Branch `chore/submission-polish` tetap terpisah dan tidak di-merge pada pekerjaan ini.

## Kesimpulan

Pemakaian langsung API yang terdampak tiga CVE tidak ditemukan pada kode yang
ditinjau. Grep permintaan tim menghasilkan nol kecocokan; pemeriksaan import AST
juga mencakup verify/ dan210file Python. Itu bukti statis terbatas, bukan jaminan
bahwa seluruh dependency transitif atau perilaku dinamis tidak dapat menjangkau
API tersebut. Pembuatan/pembacaan sertifikat X.509 yang dipakai proyek tidak sama
dengan pemakaian verifier chain yang disebut advisory.

Dependency aktif dinaikkan ke `cryptography>=50.0.2,<51` untuk infra/toolkit dan
pin `50.0.2` untuk benchmark/verify. Versi50.0.2 adalah rilis stabil yang diperiksa
di PyPI; dokumentasi mencatat wheel memakai OpenSSL4.0.3. Tidak memakai versi51
yang masih development atau menonaktifkan TLS sebagai jalan keluar.

## Advisory dan keberlakuan

| Advisory | Jalur yang dijelaskan maintainer | Versi perbaikan | Penilaian kode proyek |
|---|---|---|---|
| [CVE-2026-69248 / GHSA-m2h6-j472-rp4c](https://github.com/pyca/cryptography/security/advisories/GHSA-m2h6-j472-rp4c) | Verifikasi chain/wildcard DNS name constraints |49.0.0| Tidak ditemukan penggunaan langsung PolicyBuilder/x509.verification |
| [CVE-2026-69249 / GHSA-jwv3-5hgf-82ww](https://github.com/pyca/cryptography/security/advisories/GHSA-jwv3-5hgf-82ww) | Duplikasi self-signed intermediate menyebabkan pembesaran waktu path building |49.0.0| Verifier terkait tidak dipakai langsung menurut grep/import audit |
| [CVE-2026-69247 / GHSA-g6cj-pr64-35w5](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5) | Oracle pada decrypt PKCS#7 EnvelopedData |50.0.0| Tidak ditemukan import/pemakaian pkcs7; field/backup memakai AEAD |
| [GHSA-537c-gmf6-5ccf](https://github.com/pyca/cryptography/security/advisories/GHSA-537c-gmf6-5ccf) | OpenSSL yang disertakan dalam wheel lama |48.0.1| Tidak ditutup hanya berdasarkan grep kosong; wheel50.0.2 diuji untuk upgrade |

Sumber tambahan: [changelog50.0.2](https://cryptography.io/en/50.0.2/changelog/),
[metadata PyPI](https://pypi.org/pypi/cryptography/json), dan
[advisory OpenSSL yang dirujuk maintainer](https://openssl-library.org/news/secadv/20260609.txt).
Penilaian ini hanya empat advisory yang diminta; bukan sertifikat semua CVE sistem bersih.

## Pemeriksaan dan uji

Perintah grep yang direkam sebelum penambahan dokumen ini:

```powershell
git grep -n -E 'PolicyBuilder|x509\.verification|pkcs7' -- toolkit infra scripts app migration benchmark
```

Exit1 dengan nol baris berarti tidak ditemukan, bukan kegagalan menjalankan Git.
AST memeriksa import langsung termasuk bentuk alias/import dari parent module.
Tidak mengevaluasi seluruh dynamic import atau source dependency pihak ketiga.
Audit mengecualikan prototipe lama apps/ dan referensi buku docs/reference/.

Uji dilakukan dalam virtualenv baru di luar repo dengan cryptography50.0.2;
virtualenv/deployment/layanan existing tidak di-upgrade oleh perintah pengujian.

- Toolkit sendiri:108PASS/1SKIP. Integrasi OpenBao disposable tetap opt-in.
- Gabungan toolkit+TLS/sertifikat+crypto backup:156PASS/1SKIP.
- Tambahan model migrasi/rotasi/vector:25PASS/1SKIP, sebagian test vector overlap;
  jangan menjumlahkannya sebagai181test unik.
- CLI verifier kontrak:8pemeriksaan PASS (AAD, blob/round-trip, tamper,
  swap record/kolom, nonce sampel, normalisasi dan bidx).
- `pip check` lulus pada environment uji. Dry-run resolver infra+benchmark+verify+
  toolkit lulus; pin C yang baru mencegah konflik `<47` melawan toolkit50.

Unit test tetap memakai data buatan sendiri; tidak membaca/mengubah dataset
panitia, PostgreSQL existing atau state OpenBao. Tidak ada formatblob/AAD/bidx,
policy, key material atau ciphertext yang diubah. Shared vectors tidak diregenerasi.

## Penerapan dan koordinasi

1. Review/merge fix ini melalui alur tim. Pada checkout source baru, install ulang
   toolkit dan requirements aktif di environment target yang dipilih operator.
   Pull saja tidak memperbarui package yang sudah terpasang.
2. Pin benchmark/verify ikut diperbarui hanya untuk kompatibilitas dependency
   install baru; kode eksperimen dan hasil historis tetap utuh. Replay eksperimen
   lama menggunakan checkout/manifest/environment historis yang sesuai.
3. Periksa versi cryptography dan OpenSSL wheel pada runtime sebenarnya, lalu
   lakukan smoke/acceptance layanan terkontrol dan restart service sesuai jadwal.
   Uji lokal ini tidak mengesahkan semua VM/Linux/container telah ter-upgrade.
4. Regenerasi SBOM untuk build baru setelah fix digabung ke branch submission.
   BOM/metadata benchmark lama tetap menyebut versi yang benar-benar diukur;
   jangan menulis50.0.2 seolah dipakai pada benchmark46.0.7 sebelumnya.
5. Prototipe apps/api dan referensi buku masih mempunyai deklarasi lama pada
   main, di luar runtime app/ yang dituju fix. Perapian submission menghapus
   prototipe; jangan menyatakan seluruh repo/riwayat sudah bebas pin lama.

TLS HTTPX/http.client memakai Python ssl/OpenSSL terpisah dari backend OpenSSL
wheel cryptography. Meng-upgrade wheel tidak otomatis memperbarui Python ssl,
PostgreSQL atau OpenBao. Deployment/build image dan komponen tersebut mempunyai
proses pembaruan sendiri. Tidak perlu re-encrypt data hanya untuk upgrade library
yang lulus vector kontrak; key dan format v1 tetap sama.

Evidence: `evidence/crypto/cryptography-api-review.json`,
`cryptography-50-review.json`, `cryptography-50-vectors.json`, dan dua JUnit
`cryptography-50-tests.xml`/`cryptography-50-compatibility-tests.xml`.
