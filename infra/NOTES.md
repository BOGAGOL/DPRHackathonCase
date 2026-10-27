# Modul A — Tahap 1 infra

## Pembaruan keputusan dan penerapan — 27 Oktober 2026

Bagian Tahap 1 di bawah merekam kondisi historis. Keputusan terbaru: seluruh DB
proyek pada pg-dpr PostgreSQL 18 port host 5433; Compose Modul A hanya OpenBao
8200. Opsi proyek 5434 dihapus. Fixture PG18 disposable dipisah ke infra/tests/.
Konfigurasi mesin ada di infra/database-targets.json; helper migration/connection
memagari target protected_734/protected_100k dan sumber read-only, TLS verify-full.

Awalnya pg-dpr tidak ditemukan pada Docker context lokal. Pengguna mengklarifikasi
bahwa instance resmi ada di laptop teman dan secara eksplisit meminta clone
development lokal. Container baru pg-dpr dibuat **hanya di laptop ini** dengan
named volume pg-dpr-data, PG18 parent mount, password CSPRNG via env Docker.
Kredensial tersimpan sebagai PSCredential Windows DPAPI di luar repo (ACL operator).
Instance resmi, container, dan data laptop lain tidak diakses/diubah.

TLS diaktifkan di container lokal setelah bootstrap dengan sertifikat leaf
terpisah ditandatangani CA lokal, server.key owner postgres/0600 pada volume.
ALTER SYSTEM empat parameter + pg_reload_conf, tanpa recreate atau restart
postmaster. Snapshot SSL overrides/HBA/auto.conf di luar repo; rollback hanya
mengembalikan setting SSL terkait dan HBA yang hash-nya masih cocok, tidak RESET
ALL/menimpa perubahan lain. Leaf 30 hari, TLS minimum 1.2. hostnossl reject IPv4
dan IPv6 untuk baseline_100k/protected_734/protected_100k, setelah TLS verify-full
berhasil; aturan autentikasi lain dan Unix socket dipertahankan. Existing session
tidak diputus. Koneksi sumber asli postgres juga memakai TLS dari client A.

Sumber privat sql/baseline/02_data.sql ditemukan lokal, tetap gitignored. Initial
population ke DB postgres **baru/kosong** memakai lexer scanner non-executing dan
INSERT berparameter, tanpa plaintext temp di container; tabel sumber yang sudah
ada ditolak. Sesudah import, validasi/read checksum saja: **734**, KTP unik **734**,
panjang NIK **14/14**, kawin/tanggal **367/367**. Checksum sumber cocok evidence C.

baseline_100k lokal dibuat dengan generator C rows=100000/seed=42 dan checksum
**e6cdc975a397e1e1d2020bc476a51103d1799c38e28a1c35f6284564aef698ff**, identik
laporan resmi. Writer evidence C diarahkan sementara dalam proses ke
evidence/development/, dipulihkan finally. Tidak mengubah kode C atau overwrite
evidence/datasets/baseline_100k.json resmi. Semua evidence development diberi
official_benchmark=false. Protected DB dibuat kosong, **belum** skema/migrasi.

Hasil akhir:

- Verifikasi SQL read-only pada empat DB memakai verify-full, pg_stat_ssl
  mengonfirmasi **TLSv1.3**; checksum sumber + baseline dihitung ulang via streaming
  cursor dan keduanya cocok laporan resmi. Evidence: evidence/development/verify.json.
- Uji container PG18 disposable: **19 check lulus** untuk reload, rollback otomatis/
  eksplisit, idempotensi HBA, mode key, row sintetis tetap, ID container dan waktu
  start postmaster tetap. Evidence: evidence/infra/postgres-tls-integration.json.
- Gabungan aplikasi/infra/toolkit **176 test lulus, 1 skip** dataset opsional,
  1 warning deprecation Starlette lama. Datagen+scanner terpisah **152 lulus,
  1 skip** DB test opsional. XML di evidence/infra/pg-dpr-*-regression*.xml.
- Readiness harus menunggu TCP server final; initdb sementara hanya socket tidak
  boleh dipakai sebagai tanda siap untuk mengubah konfigurasi atau membuat DB.
- OpenBao lokal HTTPS 8200 berjalan, **initialized=false/sealed=true**, menunggu
  bootstrap/unseal manual sesuai runbook. Toolkit test memakai server disposable.
- API lama/Compose PostgreSQL 17 milik B tidak diubah. Panduan pemilihan MODE,
  endpoint pg-dpr, CA publik, dan batas scope disediakan di infra/postgres/README.md.
  TLS pada instance resmi teman masih perlu diterapkan di laptop/context miliknya.

## Batas tahap dan adaptasi referensi

Membaca AGENTS.md, PROJECT_CONTEXT, CONTRACT, TEAM_PLAN dan prompt modul A.
Paket buku di docs/reference/onno-code/data-leak-proof-postgresql dibaca sebagai
rujukan: Compose, codec, blind index, OpenBao client, migrasi, dan semua scripts/*.sh.
Kode di infra/ mengadaptasi desain sesuai kontrak, tidak mengubah referensi atau
aplikasi lama. Tahap 2–5 (toolkit, profile/skema, migrasi, backup streaming) adalah
tahap lanjutan; backup.sh yang meninggalkan plaintext tidak digunakan di jalur ini.

## Keputusan TLS dan database

- OpenBao dipin ke 2.5.5, mode server persisten, file storage pada volume terpisah.
  Versi ini sudah menghapus dukungan mlock; konfigurasi disable_mlock=false dari
  kebiasaan Vault lama ditolak server. Tidak memakai konfigurasi/capability itu.
  Lindungi swap host secara terpisah; tidak mengklaim memori terkunci.
  Uji Docker Desktop 28.0.4 juga menemukan internal:true membuat publish port
  tidak tersedia dari host. Memakai dua bridge terpisah dengan publish loopback;
  egress container belum difilter. Jangan mengklaim network ini air-gapped.
- TLS wajib; CA lokal self-signed menandatangani sertifikat server 30 hari.
  CA/private keys dan sertifikat berada di DPR_SECRETS_DIR di luar repo.
  DACL Windows hanya memberi akses operator saat ini; POSIX memakai 0700/0600.
  Tidak ada skip verify atau fallback HTTP. CA signing key tidak dipasang ke container.
- PostgreSQL opsional memakai image major 18, volume baru dan port 5434, profil
  new-postgres. Tidak ada koneksi/query ke database postgres berisi 734 baris.
  Pengguna dapat memakai pg-dpr yang sudah ada pada 5433. PG18 mount parent
  /var/lib/postgresql mengikuti tata letak image PG18. Password dari env; kosong
  membuat image PostgreSQL menolak bootstrap. Port hanya loopback.
- PostgreSQL pada profil lab ini belum diberi TLS server; jaringan data dipisah
  dari key plane. Jangan mengklaim seluruh data plane sudah dilindungi TLS.
- File storage satu node dan CA lab bukan rancangan HA/PKI produksi. Renewal
  sertifikat harus direncanakan sebelum 30 hari; generator menolak overwrite.

## Pengujian

Perintah test: `python -m pytest infra/tests -q`.
Test memverifikasi chain/SAN/masa berlaku TLS, penolakan direktori repo,
proteksi file eksklusif/ACL, dan isolasi konfigurasi Compose.

## Bootstrap dan batas policy

- Init manual membuat 3 shares, threshold 2, menulis eksklusif dan fsync ke
  external openbao/init-material.json. Tidak mencetak root/shares. Unseal hanya
  lewat perintah operator dengan prompt tersembunyi, satu share tiap pemanggilan.
- Penyimpanan gabungan sementara diberi peringatan eksplisit; pemisahan kustodian
  dan custody root offline adalah langkah operator. Tidak ada auto-unseal atau
  pembacaan otomatis shares/root oleh service.
- Root hanya dipakai configure/issue oleh admin. Empat token orphan, no default
  policy, non-renewable, explicit_max_ttl = TTL (default 3600 s; maksimum 14400 s).
  Aplikasi mengambil token workload melalui env. AppRole/renewal belum dibuat.
- svc-app dapat encrypt/decrypt PII dan FIN serta HMAC. Pembatasan dekripsi FIN
  hanya di endpoint finance merupakan kewajiban aplikasi B: token svc-app yang
  sama tidak bisa membedakan HTTP endpoint aplikasi. Jangan mengklaim isolasi
  endpoint finance ditegakkan oleh ACL Transit ini.
- svc-migration mendapat encrypt/datakey kedua KEK + HMAC, tanpa decrypt.
  Datakey plaintext diizinkan untuk enkripsi lokal; wrapped saja tidak memberi
  DEK yang diperlukan migrasi tanpa hak decrypt. Alternatif utama: CSPRNG lokal
  32 byte lalu encrypt KEK. DEK tidak boleh disimpan dalam file/log.
- svc-verify menolak seluruh Transit. key-operator hanya metadata/rotate/rewrap
  dan konfigurasi min versi. allowed_parameters menolak exportable,
  allow_plaintext_backup, deletion_allowed. Tidak ada hak DB dalam token OpenBao;
  pemisahan identitas/kredensial database ditegakkan terpisah di tahap role DB.
- Global disable_upsert mencegah workload membuat key lewat endpoint encrypt.
  Reentry menolak key yang derived/exportable/backup plaintext/deletable atau
  bertipe salah; tidak mencoba mengubah key yang tak cocok secara diam-diam.
- Perintah revoke-migration mencabut token migrasi yang aktif setelah cek policy.
  Tidak ada token statis dalam kode. Admin API memverifikasi TLS dan menolak HTTP,
  origin berisi kredensial, proxy env dan redirect. Pesan error tidak berisi body.

## associated_data pada OpenBao 2.5.5

Status source: tersedia pada encrypt/decrypt di tag 2.5.5, bukan hanya dokumentasi
`next`. `context` adalah konteks derivasi key dan bukan pengganti AAD. Key di
bootstrap memakai derived=false. HTTP probe menggunakan **associated_data**
berisi base64 AAD. Desain field tetap AES-256-GCM lokal dengan DEK PII/FIN per
record dan AAD persis kontrak; dukungan AAD Transit bukan prasyarat format field.

Sumber primer yang diperiksa:

- [Release 2.5.5](https://github.com/openbao/openbao/releases/tag/v2.5.5)
- [Encrypt source 2.5.5](https://github.com/openbao/openbao/blob/v2.5.5/builtin/logical/transit/path_encrypt.go)
- [Decrypt source 2.5.5](https://github.com/openbao/openbao/blob/v2.5.5/builtin/logical/transit/path_decrypt.go)
- [Key creation source 2.5.5](https://github.com/openbao/openbao/blob/v2.5.5/builtin/logical/transit/path_keys.go)

Temuan integrasi: search-hmac harus diberi **key_size=32 (byte)** eksplisit saat
create. Default 0 pada versi ini menyebabkan respons 500, sehingga tidak boleh
mengandalkan default server. Kunci HMAC tidak diekspor; layanan memakai /hmac.

Verifier menolak identitas/root policy yang salah sebelum menjalankan probe.
Probe penolakan parameter sensitif memakai nilai false agar tidak mengaktifkan
export/backup/delete bila ACL ternyata salah. Rotasi sebenarnya hanya diuji di
instance disposable. Larangan rotate, penerbitan token, dan export diperiksa via
sys/capabilities-self agar verifikasi pada policy yang drift tidak merotasi key,
menerbitkan token tanpa pemilik, atau mengambil material key. Semua policy diberi
hak introspeksi capability milik token sendiri; bukan introspeksi token lain.
Larangan decrypt/encrypt/HMAC/datakey diuji dengan request langsung dan input
sintetis. Token/DEK/plaintext/ciphertext tidak masuk evidence.

## Hasil verifikasi akhir (26 Oktober 2026)

- Commit TLS/Compose: 10 test infra lulus; gabungan aplikasi + infra 42 lulus,
  1 skip dataset panitia. Commit bootstrap: gabungan 60 lulus, 1 skip.
- Perintah akhir: `$env:DPR_INFRA_INTEGRATION='1'; .\.venv\Scripts\python.exe -m
  pytest tests infra/tests -q --tb=short --junitxml=evidence/infra/tests.xml`.
  Hasil: **65 lulus, 1 skip** (dataset panitia tidak didistribusikan), 1 warning
  deprecation Starlette dari dependensi aplikasi lama. Tidak mengubah aplikasi B.
- `evidence/infra/integration.json`: **60 pemeriksaan lulus**, OpenBao **2.5.5**,
  PostgreSQL **18.6** (server_version_num 180006). AAD roundtrip sukses; AAD salah
  dan AAD hilang keduanya HTTP 400. CA salah/HTTP ditolak, policy/TTL sesuai,
  pencabutan migrasi berhasil, rotate/rewrap/config berhasil, restart memerlukan
  unseal lagi dan key tetap bekerja, revokasi root tidak mencabut token orphan.
- Semua container/volume integration acak sudah dibersihkan. Container lab utama
  `dpr-infra-openbao-1` disiapkan dengan CA eksternal dan endpoint HTTPS yang
  terverifikasi; **belum initialized dan masih sealed**. Init/unseal manual di
  README adalah langkah operator, bukan auto-unseal oleh service/Compose.
  CA lab berada pada DPR_SECRETS_DIR di luar checkout, bukan di Git.
- Scope selesai: implementasi dan pengujian Tahap 1. Toolkit field AEAD/AAD dan
  backup streaming yang mengoreksi celah referensi adalah Tahap 2 dan Tahap 5;
  belum diimplementasikan di pekerjaan Tahap 1 ini dan tidak diklaim selesai.

## Pengecualian TLS baseline di laptop benchmark (28 Oktober 2026)

Atas keputusan eksplisit tim, branch `fix/tls-baseline-exception` mempertahankan
akses baseline_100k/baseline_1m tanpa TLS hanya untuk bench_user/scanner_user dari
IP Docker host yang diamati PostgreSQL, memakai SCRAM. Semua protected dan role
lain tetap terkena aturan penolakan non-TLS. Tidak ada perubahan data/privilege
baseline dan tidak ada benchmark yang diulang. Perubahan ini menunggu persetujuan
Alby sebelum merge ke main. Aturan auth yang ada dipertahankan byte demi byte
di luar blok terkelola; snapshot dan mekanisme rollback tetap digunakan.

Pemeriksaan apply/verify memakai login baseline yang nyata dan uji penolakan HBA
(bukan sekadar password salah). Login app verify-full diuji pada setiap protected
yang sudah ada; target yang belum dibuat dinyatakan pending, kemudian diverifikasi
ulang setelah prepare. Uji otomatis memakai data sintetis dan container disposable,
termasuk upgrade HBA lama, apply berulang, serta rollback otomatis/eksplisit.
Hasil: 206 test unit lulus, 5 integration opt-in dilewati; uji TLS disposable
opt-in dijalankan terpisah dan lulus (1 test). Setelah penyesuaian pembacaan
credential existing, 15 test unit TLS kembali lulus.
