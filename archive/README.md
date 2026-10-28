# Arsip prototipe awal

Folder ini menyimpan dokumen dan hasil awal PostgreSQL 17. Isinya bukan acuan
aplikasi aktif, bukan bukti kelulusan kontrol saat ini, dan tidak masuk paket pengumpulan.

Runtime lama (`apps/`, `infrastructure/`, skrip root, test lama dan `docker-compose.yml`)
dihapus dari snapshot pengumpulan. Salinannya tetap dapat dilihat pada commit Git
`88b1de7991662fc6ee6abbde6f18add22640a7f5`, sebaiknya melalui worktree terpisah.
Jangan menimpa aplikasi aktif dengan file lama untuk mereproduksi hasil terkini.

Aplikasi aktif hanya `app/`; infrastruktur berada di `infra/`, memakai PostgreSQL 18,
OpenBao 2.5.5, dan `docs/contracts/CONTRACT.md`. Tautan relatif di dalam dokumen arsip
dipertahankan sebagai catatan historis dan sebagian dapat sudah tidak berlaku.
