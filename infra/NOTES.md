# Modul A — Tahap 1 infra

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
