# Role database tahap 3

Role global cluster: `schema_owner` NOLOGIN; tujuh service login tidak memiliki
SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS, tidak mewarisi role lain dan
tidak menjadi anggota owner. Script menolak atribut/membership existing yang
berbahaya, bukan diam-diam melanjutkan. Hak objek diberikan per database target.
Role di cluster dipakai bersama protected_734 dan protected_100k, password sama.
Penerapan ulang tidak merotasi password; rotasi perlu prosedur admin tersendiri.

| Login | Hak objek |
|---|---|
| app_user | SELECT/INSERT/UPDATE anggota dan app_users; scope sendiri read-only via RLS; append audit |
| analyst_user | SELECT analyst_view dan EXECUTE analyst_age_summary() |
| auditor_user | SELECT audit_log |
| backup_user | SELECT tabel/view/sequence yang diperlukan dump, termasuk akun (hash saja) dan audit |
| admin_user | CRUD app_users/access_scope, SELECT audit; tanpa akses data anggota |
| migration_user | SELECT/INSERT/UPDATE anggota, append audit; sementara |
| scanner_user | SELECT anggota (ciphertext) dan analyst_view |

Semua service tidak mempunyai CREATE pada public, CREATE/TEMP database, atau
hak DDL/member owner. PUBLIC tidak mempunyai hak tabel/sequence/fungsi. Default
privileges milik schema_owner menutup PUBLIC; EXECUTE fungsi dicabut **global**
karena REVOKE per schema tidak membatalkan default global. Objek baru hanya
mendapat SELECT untuk backup; hak runtime lain perlu GRANT eksplisit.

psql18 membaca env ke variabel `app_user_password`, dst melalui `\getenv`.
Nama env: DPR_APP_USER_PASSWORD, DPR_ANALYST_USER_PASSWORD,
DPR_AUDITOR_USER_PASSWORD, DPR_BACKUP_USER_PASSWORD, DPR_ADMIN_USER_PASSWORD,
DPR_MIGRATION_USER_PASSWORD, DPR_SCANNER_USER_PASSWORD. Jangan isi literal
password di SQL. Gunakan wrapper pada [NOTES skema](../protected/NOTES.md).

`backup_user` juga NOBYPASSRLS. Policy SELECT semua record khusus backup membuat
`pg_dump --enable-row-security` membaca semua baris, dibuktikan dengan restore
dan count pada test sintetis. Tanpa flag itu, pg_dump default row_security=off
akan gagal pada tabel RLS. Tahap backup wajib menyertakan flag ini, TLS dan
stream enkripsi; tidak membutuhkan token OpenBao. Artefak dump test hanya ada
di memori dan tidak mengandung plaintext field PII/FIN. Produksi perlu mencabut
LOGIN/CONNECT/hak migration_user setelah migrasi (tahap 4), bukan sebelum itu.

Rujukan: [pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html),
[ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/18/sql-alterdefaultprivileges.html),
[psql](https://www.postgresql.org/docs/18/app-psql.html).

Tahap 4 menambahkan migration_jobs: migration_user SELECT/INSERT/UPDATE dan
backup_user SELECT. app/analyst/auditor/admin/scanner tidak mendapat hak kontrol
progres. Tabel dibuat oleh schema_owner lewat 02_migration.sql sebelum GRANT.
