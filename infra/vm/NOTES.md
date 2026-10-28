# Keputusan paket VM Modul A

Pengguna meminta paket/prosedur yang dijalankan Zhafif sendiri pada VM baru;
tidak ada SSH atau perubahan resource VM yang dilakukan Alby untuk paket ini.
Target data hanya `postgres` fresh source -> `protected_734`. Tidak membuat
baseline100k/1M atau menjalankan benchmark resmi.

## Adaptasi Ubuntu

- Native Linux memakai UID/GID dan mode file. Private directory 0700/file 0600;
  material password/token berasal dari penyimpanan privat, lalu environment proses.
  Tidak memakai serialisasi DPAPI Windows. Jalankan sebagai user non-root Ubuntu.
- OpenBao 2.5.5 menjalankan entrypoint yang dapat mengubah owner/drop user. Mount
  TLS key mode 0600 milik operator Ubuntu tidak otomatis bisa dibaca UID image.
  Compose VM memakai UID/GID operator dan SKIP_CHOWN; init job terbatas hanya
  mengatur root direktori named volume milik project sebelum OpenBao berjalan.
  Identitas runtime/project existing tidak dapat diganti diam-diam oleh helper.
  Acuan primer: [Dockerfile 2.5.5](https://github.com/openbao/openbao/blob/v2.5.5/Dockerfile)
  dan [entrypoint 2.5.5](https://github.com/openbao/openbao/blob/v2.5.5/.release/docker/docker-entrypoint.sh).
- Config OpenBao/TLS dan toolkit yang ada dipakai ulang. Root dan signing key CA
  tidak dipasang ke container. Leaf certificate bawaan berlaku 30 hari untuk demo;
  renewal terjadwal/PKI publik merupakan operasi terpisah, bukan klaim paket ini.
- PG18 menyimpan named volume pada parent /var/lib/postgresql. Listener PostgreSQL
  dan OpenBao hanya loopback. PostgreSQL memakai password-file, tanpa password
  literal argv atau environment container. Nama dan volume ada pada project khusus.
- Konfigurasi log PG menonaktifkan statement/duration/parameter logging dan detail
  error row. Helper tidak mencetak driver/HTTP bodies, nilai anggota, atau secret.
  Ini bukan bukti scan S06 seluruh host; verifikasi log menyeluruh tetap pekerjaan C.

## Lifecycle dan batas klaim

1. CA baru dan Transit key baru -> migrasi ulang source, bukan menyalin ciphertext
   laptop lalu menganggap kunci bernama sama akan cocok. DEK tetap hanya di memori.
2. Init/unseal nyata tetap manual, 3 shares/threshold2. Root hanya dibaca pada
   perintah operator eksplisit bootstrap-bao/refresh-app, bukan pada verifier/runtime.
3. Token empat jam maksimum. Refresh-app hanya menerbitkan svc-app; tidak membuat
   svc-migration baru setelah migrasi selesai. Token lama perlu expiry/revokasi
   operator sesuai runbook. Root/shares awal yang tergabung adalah material bootstrap
   lab yang harus dipisah melalui penyimpanan privat/kustodian, bukan melalui Git.
4. Import memeriksa container label dan system identifier, menolak tabel existing,
   menghapus DROP dari baseline DDL, dan melakukan aggregate validation sebelum commit.
   Prosedur ini hanya untuk initial population instance DPR baru yang belum berisi
   source; tidak mengubah database sumber existing.
5. Environment compose, operator, migrasi, runtime dan trusted setup dipisah.
   Fungsi Bash memakai env -i agar runtime tidak mewarisi password admin/root.
   Pemisahan ini adalah scope credential, bukan sandbox atau pemisahan operator OS;
   user Ubuntu yang mengelola private directory dapat membaca material operator.
6. Verifier menggunakan koneksi read-only, toolkit A dan batch maksimal 100 untuk
   seluruh 734 record. Ia tidak memanggil migration.validate_all yang menulis
   progress. Verify harus mendahului mutasi bisnis B; perubahan sah setelah deploy
   tentu tidak lagi identik dengan source awal. Input/source SQL masih plaintext
   privat; klaim perlindungan tidak mencakup kebocoran seluruh salinan source/key VM.

Pengujian unit memakai nilai CSPRNG dan fixture buatan sendiri. Hasil pemasangan
VM baru hanya dapat disimpulkan setelah Zhafif menjalankan langkah dan mengirim
evidence VM. Docker Desktop lokal sedang mengembalikan 500 saat penyusunan paket;
status uji live paket dicatat terpisah dan tidak disamakan dengan uji recovery A+B
yang sudah lulus pada main sebelumnya.

Hasil paket: 98 test terkait lulus, mencakup 25 test paket VM beserta rendering
Compose CLI dan sintaks/quoting Bash aktual. Pemeriksaan logika import/retirement/
verifier memakai mock koneksi dan data buatan sendiri; bukan hasil instalasi VM.
Evidence mesin: `evidence/deployment/vm-package-tests.json`. Pada deployment,
Zhafif perlu menghasilkan `vm-verify.json` dengan rows_compared=734 sebelum mutasi
bisnis B; Alby akan memvalidasi bukti VM tersebut secara terpisah.
