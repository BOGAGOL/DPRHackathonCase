# Indeks bukti — 23 Oktober 2026 WIB

| Artifact | Lingkup |
|---|---|
| `security-tests.xml` | Pytest policy, API, crypto, parser/import, backup dan konfigurasi; SQLite sementara |
| `migration.json` | PostgreSQL nyata: 734 record × 29 kolom, dekripsi equality dan blind index |
| `postgres-security.json` | Live API role behavior, runtime grants, logical dump canaries, repository current-secret scan, independent parser equality |
| `browser-tests.json` | Lima Chromium flow: empat peran, update, XSS, CSRF, IDOR, pagination, mobile dan logout |
| `backup-restore.json` | Backup protected independen terenkripsi, restore DB baru, dekripsi semua field, tamper rejection |
| `benchmark.json` | 734 record, tiga pengulangan, raw latency samples dan resources, tiga encrypted backup/restore per konfigurasi |
| `benchmark-scaled.json` | 10.000 record sintetis baru, tiga pengulangan, workload dan metrik yang sama |
| `openapi.json` | Kontrak API dan DTO, tanpa credential/data |
| `dependencies.json` | Versi/lisensi dependensi langsung dan lockfile, bukan CVE attestation |

Raw report browser, screenshot QA, secret dan file DB/backup tetap di `.local`, diabaikan Git. Export browser hanya title/status/duration, tanpa request/response, cookie atau data sumber. Raw benchmark berarti sampel durasi anonim, tidak berisi input KTP atau isi record.

Compose config dan Next build diuji melalui perintah dalam PROGRESS; runtime container **NOT TESTED**. Live OpenBao, semua transport TLS, physical volume/WAL encryption, rotasi Transit, retensi otomatis, benchmark HTTP/TLS dan fresh-clone host kedua **NOT TESTED**. Hasil ini bukan sertifikasi keamanan atau kepatuhan legal.
