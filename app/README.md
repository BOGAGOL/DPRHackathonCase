# Service Application — Modul B

Aplikasi aktif berada di `app/`: FastAPI/SQLAlchemy + Next.js/TypeScript.
Satu kode mendukung `MODE=plain` pada baseline dan `MODE=protected` pada target
protected PostgreSQL 18. TLS verify-full wajib di runtime. Protected gagal tertutup
bila TLS, token, key atau autentikasi ciphertext gagal; tidak ada fallback plaintext.

## Mulai dari satu panduan

Untuk juri/pengembang baru, gunakan **[panduan reproduksi lengkap](../docs/operations/REPRODUCTION.md)**.
Launcher di root menyiapkan 734 record, toolkit nyata, enam akun dan HTTPS tanpa
menyalin konfigurasi developer. Jangan mengikuti dokumentasi prototipe `archive/`.

```powershell
python -m infra.reproduce setup
python -m infra.reproduce demo --data "C:/private/02_data.sql"
```

Akun acak dan private key tidak dicetak; lokasi file privat ditampilkan launcher.
Setiap start merupakan stack baru, bukan provisioning ulang deployment existing.
Untuk server existing gunakan runbook khusus di bawah.

## Interface dan akses

- Enam peran: `operator`, `privileged_officer`, `finance_officer`, `anggota`,
  `analyst`, `auditor`. Assignment record eksplisit; anggota hanya record sendiri.
- [Matriks akses](ACCESS_MATRIX.md) dan [policy aktual](backend/service_app/policy.py)
  menentukan field yang dikirim. Backend membentuk DTO; menyembunyikan di UI saja
  tidak menjadi kontrol akses. Format masking UI mengikuti policy B; format toolkit
  contoh panitia terpisah, jangan menyamakan keduanya.
- Analytics membaca **`public.analyst_summary`**, bukan `analyst_view` per record.
  Lima marginal, count≥5, label kelompok kecil tidak dikirim; `total=null`.
  Filter cohort gabungan yang belum mempunyai interface suppression ditolak.
- Argon2id untuk password; opaque cookie HttpOnly/Secure/SameSite Strict, CSRF,
  validasi input, SQL berparameter, respons no-store dan audit minim nilai pribadi.
- Protected memakai `dprcrypto:public-v1`; principal RLS adalah UUID akun.
  `app_user` NOBYPASSRLS, RLS merupakan lapisan tambahan. Session setting bisa
  diganti pencuri credential DB; backend tetap wajib melakukan otorisasi.
- F-01: NIK ternormalisasi duplikat ditolak HTTP 409 dan unique index bidx.
  SQL upgrade existing tidak menghapus duplikat secara otomatis.

## Panduan operasional spesifik

| Kebutuhan | Rujukan |
|---|---|
| Konfigurasi environment | [.env.example](.env.example) |
| Integrasi A/B dan toolkit | [Integrasi](docs/INTEGRATION_A.md), [adapter](docs/CRYPTO_ADAPTER.md) |
| Upgrade analytics A5 | [Rilis A5](docs/DEPLOY_A5.md) |
| Upgrade identitas F-01 | [F-01](docs/F01_DUPLICATE_IDENTITY.md) |
| Fresh VM untuk dependensi A | [Runbook VM](../infra/vm/README.md) |
| Pemulihan tujuh tabel dan cutover | [Recovery](docs/RECOVERY.md) |
| Clone benchmark API | [Target terisolasi](docs/BENCHMARK_CLONES.md) |
| Frontend dan trust CA browser | [Frontend](web/README.md) |

`schema.py` menyiapkan tabel kontrol B setelah skema A; `provision.py` membuat
enam akun baru, menolak overwrite; `serve.py` menyalakan API HTTPS. Skrip ini bukan
perintah upgrade universal. Jangan menjalankan golden reset/provision/prepare ulang
pada server aktif hanya untuk memperbarui kode. Gunakan credential role workload,
bukan DBA/root sebagai runtime. Rahasia tetap di penyimpanan privat di luar checkout.

## Pengujian

```powershell
# Setelah setup, dari root; suite B dijalankan terpisah dari suite A/C.
.venv/Scripts/python -m pytest -c app/pytest.ini app/tests -q
```

Linux: `.venv/bin/python`. Bukti unit/SQLite/mock UI bukan acceptance PG/OpenBao.
[Acceptance nyata](../infra/acceptance/README.md) dan hasil baru launcher di
`evidence/reproduction/` menyebut scope. Hasil historis Modul B tetap berada di
`app/evidence/access-control/`; [NOTES.md](NOTES.md) menyimpan kronologi/keterbatasan.
