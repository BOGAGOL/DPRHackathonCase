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
