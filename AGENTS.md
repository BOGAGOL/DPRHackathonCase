# Aturan untuk agen AI (Codex / Claude Code) di repo ini

Proyek: Final Hackathon DPR RI 2026, Pelindungan Data Pribadi. Baca dulu `docs/contracts/CONTRACT.md`.
Kontrak itu wajib dipatuhi. Jika tugas tampak bertentangan dengan kontrak, berhenti dan tulis
pertanyaan di NOTES.md modulmu, jangan mengubah kontrak.

## Batas kerja
- Hanya ubah folder milik modulmu (lihat CONTRACT.md bagian 11). Untuk `README.md`, `Makefile`,
  `.gitignore`: hanya tambah, jangan hapus atau timpa isi yang ada.
- Database `postgres` (734 baris asli) tidak boleh diubah.
- Platform pengembang Windows + PowerShell. Sediakan perintah `python -m ...` atau `.ps1`; jangan
  mengandalkan `make` saja.

## Keamanan
- Kriptografi: AES-256-GCM dengan nonce acak 12 byte dan AAD sesuai kontrak. Dilarang AES-ECB/CBC,
  nonce tetap, Base64 sebagai "enkripsi", SHA-256 untuk password (pakai Argon2id), hash tanpa kunci
  untuk data berentropi rendah.
- Gagal dekripsi = error. Dilarang fallback plaintext.
- Tidak ada kunci, token, password di kode, test, log, atau output. Kredensial dari env var.
- Query selalu berparameter. Log tidak berisi nilai data pribadi.
- Data uji harus sintetis buatan sendiri; jangan menyalin isi dump ke test fixture.

## Kualitas
- Setiap fungsi baru punya test. Jalankan test sebelum selesai.
- Setiap skrip verifikasi menulis hasil mesin (JSON/CSV) ke `evidence/<kategori>/`.
- Tulis keputusan, asumsi, dan keterbatasan di `<modul>/NOTES.md`.
