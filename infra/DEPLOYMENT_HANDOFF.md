# Handoff deployment VM baru — 28 Oktober 2026

Target terbaru dari pengguna adalah **ubuntu@43.156.157.247**, bukan akun agenz pada
server sebelumnya. Path yang diminta: kode `~/juara1onno`, material operasional
privat `~/dpr-demo-zhafif/private`. Keberadaan/izin folder belum diverifikasi di VM.
Status preflight: [ssh-preflight.json](../evidence/deployment/ssh-preflight.json).

Perbaikan recovery A/B sudah merged ke main melalui PR #7, merge commit `4c33b24`.
Test deployment ke VM berbeda dari empat test recovery yang sudah lulus pada
container sementara lokal. VM ini belum dikonfigurasi oleh sesi ini.

## Yang diperlukan sebelum dapat masuk

Public key khusus laptop Alby sudah dibuat pada Windows:

`%USERPROFILE%\.ssh\dpr-demo-alby\id_ed25519.pub`

Hanya file `.pub` itu yang diteruskan kepada pemilik/operator VM untuk dipasang
pada akun **ubuntu**. Ini identitas laptop Alby, terpisah dari public key Zhafif.
Private key berada di luar repository pada direktori dengan ACL user Windows
saat ini. Isi private key, password, root token dan unseal share tidak dimasukkan
ke repository atau pesan.

Operator VM juga perlu mengonfirmasi fingerprint host SSH dari console VM atau
jalur tepercaya. Probe strict saat ini berhenti pada host-key verification;
belum membuktikan apakah autentikasi public key diterima. Pengecekan host key
tidak dinonaktifkan. Tidak ada perintah remote atau perubahan server yang dijalankan.

## Urutan setelah akses SSH tersedia

1. Periksa OS, kapasitas, layanan, Docker, port dan folder yang sudah ada secara
   read-only. Konfirmasi izin direktori, resource/port DPR dan subdomain dengan
   pemilik VM sebelum mengubah routing atau resource bersama.
2. Siapkan PostgreSQL 18 dan OpenBao 2.5.5 pada resource khusus DPR. Terapkan TLS,
   role minimum serta private directory di luar checkout. Jangan memakai atau
   menimpa database/container Agenz yang sudah ada. Nama resource dan port harus
   ditetapkan setelah inventaris server; port lokal kontrak pengembang adalah 5433.
3. Untuk VM fresh, pilihan utama adalah membuat key plane baru dan **migrasi ulang
   734 record** pada VM menggunakan kunci VM itu. Menyalin database protected dari
   laptop lalu membuat OpenBao baru dengan nama kunci sama tidak cukup: material
   KEK harus benar-benar cocok untuk membuka wrapped DEK. Pemindahan key plane
   existing memerlukan prosedur backup/pemulihan kunci tersendiri.
4. Init OpenBao hanya setelah memastikan instance benar-benar baru; simpan material
   bootstrap di private directory dan lakukan unseal manual sesuai runbook A.
   Terbitkan identitas svc-app TTL terbatas untuk aplikasi; root bukan identitas
   runtime. Sertifikat/CA dan password/token server disediakan secara privat.
   Credential XML DPAPI laptop Windows tidak dipakai sebagai credential Linux.
5. Terapkan schema/role, migrasi dan decrypt-and-compare seluruh 734 record, lalu
   setup kontrol B, enam akun dan assignment record yang eksplisit. Source 734
   tidak diubah setelah initial import pada instance DPR yang baru. Dataset tetap
   privat; tidak disajikan melalui web atau lampiran publik.
6. Jalankan aplikasi dengan role runtime minimum, TLS verify-full DB/OpenBao,
   HTTPS API/web serta APP_ORIGIN sesuai subdomain yang disepakati. Routing publik
   mengikuti konfigurasi pemilik VM, tanpa mengganti routing layanan lain.
7. Uji enam peran melalui HTTPS, scope/IDOR, field yang diizinkan, pencarian, update,
   insert, fail closed, serta backup/restore lengkap tujuh tabel. Simpan evidence
   VM terpisah dari evidence laptop dan benchmark resmi.

Panduan yang dipakai setelah akses tersedia: [infra](README.md),
[migrasi](../migration/README.md), [integrasi A/B](../app/docs/INTEGRATION_A.md),
dan [backup/recovery layanan](../app/docs/RECOVERY.md).

Kebutuhan pemilik VM saat ini: pemasangan public key ubuntu, fingerprint SSH yang
terverifikasi, izin folder/resource khusus DPR, dan domain/routing HTTPS. Detail
operasional PostgreSQL/OpenBao serta aplikasi disiapkan setelah akses tersebut tersedia.
