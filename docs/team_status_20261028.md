# Audit status Modul A dan B — 28 Oktober 2026

Audit read-only 15:14:04–15:35:27 WIB (batas 15:54:04). Main `ed88ecde7110`, A `b8e999815f20`, B `9029b77ee468`, branch C `ed9e1f01634c`. Tidak mengakses PostgreSQL/OpenBao, tidak menjalankan benchmark/migrasi/restore/rotasi/merge. Hanya dua laporan audit dibuat.

Acuan `main` pada temuan adalah **origin/main**; branch lokal main tetap `5ab5248f499b` dan tidak disentuh.

SELESAI+BUKTI selalu dibatasi scope yang disebut. Lab Alby, lab Zhafif, disposable dan laptop benchmark dibedakan. Detail per butir: commit, hash berkas, waktu event/commit WIB dan catatan ada di [JSON audit](../evidence/integration/team_status_20261028.json). Waktu event null tidak diganti dengan waktu commit.

| ID | Status | Temuan | Bukti utama (path:baris) |
|---|---|---|---|
| A1 | SEBAGIAN | Streaming/HMAC, restore dua mode, tamper/retention PASS lab Alby; pemulihan HTTP belum terbukti. | `scripts/backup/runner.py:53`; `scripts/backup/crypto.py:106`; `scripts/backup/postgres.py:111` |
| A2 | SELESAI+BUKTI | PII KEK1->2, rewrap 100.734, full validation dan backup pra-rotasi PASS di lab Alby. | `infra/rotation/runner.py:1`; `evidence/keys/rotation-first-attempt.json`; `evidence/keys/rotation.json` |
| A3 | SELESAI+BUKTI | Vector ada; verifier dan test toolkit dijalankan audit PASS. | `docs/contracts/test_vectors.json`; `toolkit/tests/test_vectors.py:14`; `evidence/crypto/vectors.json` |
| A4 | SELESAI+BUKTI | 8 parameter tamper/swap fail-closed dijalankan audit PASS. | `toolkit/tests/test_codec.py:33`; `toolkit/dprcrypto/codec.py:49`; `evidence/crypto/vectors.json` |
| A5 | SEBAGIAN | DB analyst masih melihat REF per record; GROUP BY tanpa suppression; test menerima total 3. | `sql/protected/01_schema.sql:202`; `sql/roles/01_roles.sql:113`; `infra/tests/test_protected_schema_integration.py:101` |
| A6 | SEBAGIAN | Lab A: revoke+NOLOGIN+734 PASS. Laptop benchmark: NOLOGIN, protected_734 masih pending. | `evidence/migration/completion.json`; `evidence/migration/validation-protected_734.json`; `evidence/migration/revocation.json` |
| A7 | SEBAGIAN | Bao localhost:8200/TLS; PG18 bootstrap localhost:5433->5432; paket server terpadu belum ditemukan. | `infra/compose.yaml:12`; `infra/openbao/openbao.hcl:9`; `infra/postgres/development.py:60` |
| A8 | TIDAK DITEMUKAN | Draf bab A tidak ditemukan; yang ada runbook/NOTES/evidence. | `docs/TEAM_PLAN.md:34` |
| B1 | SEBAGIAN | PR1 dan PR6 MERGED, branch B bersih; review anggota lain tidak tercatat. | [PR #1](https://github.com/BOGAGOL/juara1onno/pull/1); [PR #6](https://github.com/BOGAGOL/juara1onno/pull/6); metadata review di JSON |
| B2 | SELESAI+BUKTI | Runtime mengimpor dprcrypto; vector B PASS 8 checks, sama dengan A. | `app/backend/service_app/crypto.py:46`; `app/tests/conftest.py:33`; `app/tests/test_protected_scope.py:43` |
| B3 | BELUM | Migrated protected_734/100k resmi NOT TESTED; PASS hanya disposable nyata dan plain lab Zhafif. | `app/evidence/access-control/protected-integration.json`; `app/evidence/access-control/readiness.json`; `app/evidence/access-control/baseline-100k.json` |
| B4 | SEBAGIAN | Jumlah<5 disensor dan diuji, tetapi label kelompok kecil tetap dikirim/ditampilkan. | `app/backend/service_app/analytics.py:5`; `app/tests/test_analytics_suppression.py:8`; `app/web/src/app/(service)/analytics/page.tsx:37` |
| B5 | SEBAGIAN | HTTP500 generik/swap PASS disposable; parity aplikasi target nyata belum terbukti. | `app/backend/service_app/main.py:155`; `app/tests/test_access_control.py:97`; `app/tests/test_access_control.py:274` |
| B6 | SEBAGIAN | Endpoint 7 ada; DTO/scope tidak sama dengan DB; rollback tulis protected/1M belum tersedia. | `app/scripts/serve.py:17`; `app/backend/service_app/main.py:292`; `app/backend/service_app/main.py:318` |
| B7 | SEBAGIAN | HTTPS launcher/password random ada; Dockerfile/compose deploy app final belum ada. | `app/scripts/serve.py:13`; `app/web/server.mjs:1`; `app/scripts/provision.py:68` |
| B8 | TIDAK DITEMUKAN | Draf Bab7/narasi laporan B tidak ditemukan. | `app/docs/INTEGRATION_A.md:1`; `docs/TEAM_PLAN.md:34` |
| C1 | SELESAI+BUKTI | Blob/AAD/normalisasi/bidx cocok; proyeksi API vs DB berbeda dan harus dipisahkan. | `docs/contracts/CONTRACT.md:101`; `docs/contracts/CONTRACT.md:110`; `toolkit/dprcrypto/codec.py:21` |
| C2 | SELESAI+BUKTI | Regex scope diff selesai; tidak ada secret aktif terkonfirmasi. Bukan full-history S05. | `app/README.md:60`; `app/web/tests/ui.spec.ts:13`; `benchmark/tests/test_1m_crosscheck.py:29` |
| C3 | SEBAGIAN | A/B sudah main; run gabungan bersih; suppression, integrasi app dan review masih menghalangi klaim selesai. | `docs/PROJECT_CONTEXT.md:156`; `docs/TEAM_PLAN.md:34`; `sql/protected/01_schema.sql:202` |

## Tiga blocker teratas

1. **A5, B4** — Suppression belum utuh: analyst DB masih per record/agregat tanpa k>=5; label kelompok kecil B masih terlihat. A batasi interface analyst dan suppression SQL; B selaraskan penghilangan kelompok kecil; tambahkan negative test.
2. **B3, B5, B6, A1, A6** — Integrasi Service App pada migrated target, paired parity, recovery HTTP dan rollback workload API belum terbukti; protected_734 resmi pending. Jadwalkan pengujian yang diizinkan pada target/fixture terpisah; samakan scope/DTO dan strategi reset tanpa mengubah artefak awal. Jangan benchmark tanpa instruksi.
3. **B1, C3** — PR1-6 tidak memiliki review formal anggota lain; branch gabungan C belum masuk main. Review lintas anggota terhadap source/evidence final dan PR run/overnight-28okt. Audit tidak membuka atau merge PR.

## Catatan per butir

- **A1** — pg_dump stdout langsung ke encrypt_stream tanpa dump plaintext temporer; manifest canonical HMAC dengan kunci terpisah, digest dan semua frame AEAD diperiksa sebelum CREATE DATABASE baru. Mode tanpa OpenBao tetap perlu kunci artefak backup, tetapi field tetap ciphertext. Restore 734/100k PASS di clone development Alby, bukan laptop benchmark. Dengan OpenBao: ACL/RLS dan smoke 16 record/392 field non-null PASS, tetapi app_users/access_scope kosong dan HTTP service recovery belum diuji. Retention membuktikan anggota sintetis hilang dari backup baru (735->734), bukan pemusnahan backup lama/scheduler purge.
- **A2** — Rotasi PII 1->2, rewrap 734+100000 baris. Percobaan pertama berhenti, resume menyelesaikan 45400 sisa; evidence jelas mencatat resumed. Semua plaintext/DEK, ciphertext FIN/bidx/REF dan jumlah baris tetap; full validation 734/100k PASS. Finance/search tetap v1, min_decryption_version tidak dinaikkan. Backup sebelum rotasi masih dapat dipulihkan/didekripsi. Bukan rotasi di laptop benchmark.
- **A3** — Vector test_only berisi kasus sintetis; tidak dicetak. test_shared_vector_file_and_corrupted_expectation dijalankan pada detached worktree main dan PASS dalam suite68. Evidence verifier A/B memiliki SHA256 vector yang sama dan delapan check PASS: AAD, blob/roundtrip, tamper, record/column swap, nonce, normalisasi, bidx.
- **A4** — test_tamper_and_swap_fail_closed meliputi key, record UUID, column, protection_version, format, nonce, ciphertext, tag. Bit dibalik pada format/nonce/ciphertext/tag; konteks record/kolom berubah dengan DEK tetap menguji AAD. Semua memicu DecryptionError. Tidak mengubah ciphertext database selama audit.
- **A5** — analyst_view SELECT REF+age_band per record; analyst_age_summary GROUP BY tanpa HAVING/suppression. analyst_user memang tidak bisa SELECT tabel dasar, tetapi diberi SELECT view tersebut. Test integrasi mengharapkan tiga baris dan total agregat tiga, bukan penolakan small-cell. Tidak ditemukan test suppression SQL k>=5. Kontrol endpoint B tidak menutup akses langsung analyst_user.
- **A6** — completion development Alby membuktikan protected_734 734 dan protected_100k 100000, revokasi token ditolak dan validasi sesudah revokasi, migration_user NOLOGIN. Laptop benchmark terakhir14:48:49 WIB juga NOLOGIN, tetapi TLS evidence mencatat protected_734 pending prepare. Token yang dicabut adalah token migrasi pada sesi itu; jangan klaim seluruh token svc-migration yang diterbitkan kemudian sudah dicabut. Tidak ada lookup token/query live saat audit.
- **A7** — infra/compose.yaml hanya Bao2.5.5 bind127.0.0.1:8200. Listener0.0.0.0 ada di dalam container dan TLS aktif. Skrip development menyediakan PG18 publish127.0.0.1:5433->5432, bukan host0.0.0.0:5432. verify-full punya evidence PASS. Manual unseal threshold2/3 dengan dua kustodian terdokumentasi; bootstrap lab masih menyimpan shares/root bersama di luar repo sementara, dengan peringatan pemisahan. Belum ditemukan paket deploy fresh server terpadu PG+Bao. Scan terbatas tidak menemukan secret aktif, bukan jaminan seluruh history.
- **A8** — Tracked tree main/branch A yang sudah ancestor main dan pencarian path laporan/chapter/bab pada history remote tidak menemukan draf bab. Tidak menganggap README/NOTES sebagai narasi laporan.
- **B1** — PR1 merge20e08f3 pada27 Okt14:10:28 WIB, PR6 mergeed88ecd pada28 Okt10:18:27 WIB. Keduanya mergedBy favianzhafif26 (pembuat PR). GitHub reviews=[] dan reviewDecision kosong; tidak ada reviewer formal yang dapat disebut. Branch B9029b77 ancestor main, dry merge bersih. Ini tidak membuktikan tidak pernah ada review di luar GitHub.
- **B2** — ToolkitAdapter memakai importlib.import_module(dprcrypto), OpenBaoClient, KeyManager, BlindIndexer dan encrypt/decrypt A. Tidak ada AES/HMAC runtime sendiri di app/backend/service_app; FakeCrypto hanya app/tests. Evidence vector28 Okt09:39:42 WIB PASS 8 check. test_actual_module_a_vectors_pass tercatat PASS. Verifier vector yang sama dijalankan audit pada A.
- **B3** — readiness secara eksplisit menyebut migrated_protected_datasets NOT TESTED. protected-integration PASS memakai schema/toolkit A dan PG18/Bao/TLS asli, tetapi database/project disposable dan fixture kecil. baseline-100k PASS MODE=plain lab Zhafif. DB adapter C parity pada target nyata bukan bukti Service App B.
- **B4** — count1-4 menjadi <5, secondary suppression/null dan total disembunyikan untuk menghambat pengurangan. Threshold1/4/5/6, filter dan secondary test tercatat PASS kedua mode; live disposable filtered_count_suppressed PASS. Namun group.dimension/value tetap dikirim dan UI merender kelompok itu. Jadi syarat literal kelompok<5 tidak tampil belum dipenuhi; yang ditutup hanya jumlah persis. Tidak ada jaminan differencing antar-query.
- **B5** — CryptoUnavailable menjadi HTTP500 generik tanpa plaintext; swap test protected PASS dan real_AAD_swap_generic_500 PASS di disposable. Matriks role/field diuji terhadap expected invented values di plain dan protected FakeCrypto. Belum ada paired parity aplikasi seluruh field/peran di dataset migrasi. Evidence unit mengaku dirty worktree; source snapshot hash tidak cocok HEAD audited pada raw/CRLF maupun git-blob/LF. Belum diketahui apakah perbedaan hanya dokumentasi.
- **B6** — Dua launcher dengan MODE/port/env berbeda bisa disiapkan. Scope staff protected contoh hanya1,2 perlu disamakan dengan key pool 2048. Search mengembalikan locator+nama, list tidak jenis_kelamin, detail sesuai role bukan seluruh29 field; definisikan workload API terpisah dan sama antar-mode. POST/PATCH commit per request. cleanup local_lab hanya satu insert baseline100k, bukan protokol rollback/reset benchmark protected/1M. Jangan mutasi artefak kondisi awal; strategi fixture/reset harus diotorisasi terpisah.
- **B7** — serve.py dan web/server.mjs wajib cert/key/HTTPS, default bindloopback; real HTTPS fixture PASS. provision secrets.token_urlsafe(24), hash Argon2id dan exclusive file privat, tanpa hardcoded demo password. app/ tidak memiliki Dockerfile/compose deploy final; compose B hanya integration/local-lab PG. apps/* Dockerfile dan root compose menunjuk implementasi lama, PG17, opsi crypto lokal dan insecure cookie default. Jangan dianggap paket B final. Reverse-proxy/server deployment belum dibuktikan.
- **B8** — Tidak ditemukan pada tracked branch B/main. README/ACCESS_MATRIX/NOTES/INTEGRATION_A dan evidence tersedia sebagai bahan, bukan draf bab.
- **C1** — A blob0x01+nonce12+ciphertext/tag16; AAD nama kolom sumber, UUID lowercase, protection_version. B/C memanggil codec sama dengan UUID internal, legacy_row_id hanya locator. NIK digit ASCII/nol awal, email trim+lower, pengguna trim case-sensitive. HMAC message bidx|v1|kolom|normalized, key_version1; Transit vault:v1:BASE64 -> bytes32 DB. bidx:v1:HEX internal B hanya binding akun, bukan format respons Transit. C mengonversi date/int, B JSON sesuai role; bukan mismatch crypto.
- **C2** — gitleaks tidak terpasang. Regex added-lines: private-key header, GitHub/Bao token, credential URL, quoted secret assignment. Diff3titik main...A/B kosong karena sudah merged. Diff2titik main..A berisi tree historis39 file, bukan pending commit. Scan tambahan merged ranges mencakup inherited team changes. Empat kandidat hanyalah README interpolation, random UI synthetic fixture, dua URL sintetis test C. Tidak ada .env/private-key/credential/init-material ter-track di main. Test vector keys sintetis; dataset panitia PRIVATE sesuai pengecualian, tidak diekspor. Tidak memindai seluruh history/log; bukan klaim S05 global.
- **C3** — A/B ancestor main dan dry merge bersih. Branch C lama konflik verify/NOTES.md; run/overnight-28okt memuat main dan seluruh C, dry merge bersih. Tidak ada merge audit. Blocker klaim selesai: DB suppression/kelompok kecil UI, belum ada target app protected/parity/rollback API, review formal lintas anggota. Draf bab dan paket server final belum ada. Gunakan branch gabungan yang sudah menyelesaikan konflik, bukan merge ulang branch C lama.

## Pengujian dan batas bukti

- **Audit A: 68 PASS, 1 deselected**, unit vector/codec/bidx/backup dengan memori/file temporer eksternal. Daftar testcase/digest JUnit tertanam di JSON; tidak ada koneksi layanan.
- Percobaan lebih luas: awalnya basetemp audit keliru di dalam worktree. Setelah dipindah keluar masih **72 PASS, 1 FAIL, 58 setup ERROR** karena ACL Windows fixture CA/DPAPI tidak dapat dibatasi. Kendala lingkungan dicatat; tidak ada patch kode/test atau klaim semua test A lulus.
- **Test B tidak dijalankan ulang**: dependency pin pydantic==2.12.5 tidak tersedia di index sesi. Existing unit evidence **276 PASS/0 FAIL/1 SKIP**,28 Okt09:51:17 WIB, SQLite/FakeCrypto. Protected disposable nyata PASS09:38:02 WIB; vector PASS09:39:42 WIB.
- Source hash unit B mengaku dirty worktree: tersimpan9d031ae6…, audited raw/CRLF c88df5e2…, LF/git-blob560ca53f…. Tidak cocok; belum diketahui apakah hanya dokumentasi. Evidence terdahulu tidak membuktikan seluruh HEAD identik.
- Backup Alby27 Okt23:31–23:32 WIB: dua mode restore734/100k PASS, tamper23:31:31 PASS, retention23:31:36 PASS. F04 terbatas DB+ACL/RLS+decrypt smoke16 record; HTTP recovery belum. F05/S07 PASS sesuai scope itu. Mode tanpa OpenBao tetap memerlukan kunci artefak/HMAC.
- Rotasi Alby28 Okt00:03:58 WIB: PII1→2, semua100734 rewrap+validate PASS; backup lama masih decrypt00:06:41 WIB. Token migrasi yang dipakai dicabut dan NOLOGIN di lab Alby. Keadaan laptop benchmark diambil dari evidence terakhir, bukan query live audit.

## Konsistensi kontrak A/B/C (C1)

| Aspek | A | B | C | Hasil |
|---|---|---|---|---|
| Blob0x01+nonce12+tag16 | toolkit/dprcrypto/codec.py:33,43,49 | app/backend/service_app/crypto.py:46,63 | benchmark/adapters/protected.py:14,67 | Codec sama |
| AAD dpr/v1/tabel/kolom/UUID/version | codec.py:21,28 | repository.py:82,88 | protected.py:62,67 | Format tepat `dpr\|v1\|anggota_protected\|<kolom>\|<UUID lower>\|<version>`; legacy locator terpisah |
| Normalisasi NIK/email/pengguna | toolkit/dprcrypto/bidx.py:8 | repository.py:15 + toolkit | protected.py:78 BlindIndexer | Digit ASCII/nol awal; trim+lower email; pengguna case-sensitive |
| bidx HMAC-SHA25632bytes | bidx.py:20,34; openbao.py:267 | crypto.py:49,59 | protected.py:78,133 | msg `bidx\|v1\|kolom\|normalized`, Transit BASE64→bytes32, pinned v1 |
| Binding B bidx:v1:HEX | — | repository.py:42 | — | Binding akun internal, bukan format HMAC Transit |

## Kesiapan API dan endpoint (B6)

Usulan dua proses/terminal terpisah setelah provisioning yang diizinkan: plain MODE=plain, database baseline_100k, API_PORT8100, WEB_PORT3443, APP_ORIGIN https://localhost:3443; protected MODE=protected, protected_100k, API8101, WEB3444, origin https://localhost:3444. Launcher: `python app/scripts/serve.py`; frontend `npm start` di app/web dengan API_INTERNAL_URL menunjuk API masing-masing. Tidak ada launcher dijalankan audit.

Masing-masing: DATABASE_URL app_user, ANALYST_DATABASE_URL, AUDITOR_DATABASE_URL dengan verify-full+CA; TLS_CERT_FILE/TLS_KEY_FILE, NODE_EXTRA_CA_CERTS. Protected memakai OPENBAO_ADDR/CACERT/TOKEN svc-app dari privat. Cookie jar terpisah per mode. Demo `<role>.demo` untuk enam role; password random hanya file privat provision. Samakan scope key pool 2048, bukan contoh dua record.

| Skenario | Endpoint | Gap |
|---|---|---|
| read_by_nik | GET /anggota/search?no_ktp= | locator+nama, bukan full29 |
| read_by_email | GET /anggota/search?email= | locator+nama, bukan full29 |
| read_profile | GET /anggota/{legacy_id} | DTO sesuai izin peran |
| list_page | GET /anggota?page= | 50 locator+nama, tanpa jenis_kelamin |
| update_contact | PATCH /anggota/{id}/kontak | CSRF; commit; belum rollback benchmark |
| insert_member | POST /anggota | privileged+insert scope; commit; belum cleanup protected/1M |
| mixed | campuran bobot20/20/20/10/15/15 | definisikan workload API terpisah |

## Branch remote dan dry merge

Git2.37: `git merge-tree <merge-base> origin/main <branch>`. Exit0 saja tidak cukup; marker konflik juga diperiksa. Tidak ada merge sungguhan atau checkout working tree utama. Branch A/B sudah ancestor main; branch gabungan run memuat main, jalur integrasi bersih.

| Remote | Hash | Author | Waktu commit WIB | Dry merge ke main |
|---|---|---|---|---|
| origin/HEAD | `ed88ecde7110` | japippppp | 2026-10-28T10:18:27+07:00 | acuan/symbolic HEAD |
| origin/feat/crypto-infra-tls | `549e6db7525e` | albyarto | 2026-10-26T22:48:42+07:00 | bersih (ancestor) |
| origin/feat/crypto-migration | `b8e999815f20` | Muhammad Albyarto Ghazali | 2026-10-28T01:10:13+07:00 | bersih (ancestor) |
| origin/feat/crypto-toolkit | `86df826d55ef` | albyarto | 2026-10-26T23:29:08+07:00 | bersih (ancestor) |
| origin/feat/scanner | `3d2d1f9ad0d0` | AhmadDzulfikar | 2026-10-26T20:45:46+07:00 | bersih (ancestor) |
| origin/feat/service-app | `9029b77ee468` | favianzhafif26 | 2026-10-28T09:51:38+07:00 | bersih (ancestor) |
| origin/feat/verify-bench | `fbeff98c1748` | AhmadDzulfikar | 2026-10-27T22:25:12+07:00 | KONFLIK: verify/NOTES.md |
| origin/fix/tls-baseline-exception | `7dcdd9e70179` | AhmadDzulfikar | 2026-10-28T00:46:36+07:00 | bersih (ancestor) |
| origin/main | `ed88ecde7110` | japippppp | 2026-10-28T10:18:27+07:00 | acuan/symbolic HEAD |
| origin/run/overnight-28okt | `ed9e1f01634c` | AhmadDzulfikar | 2026-10-28T15:05:37+07:00 | bersih |

## PR dan review

Semua PR yang dikembalikan gh pr list --state all sudah MERGED; tidak ada PR terbuka. Semua reviews=[] dan reviewDecision kosong. Ini bukan bukti tidak ada percakapan di luar GitHub; review formal anggota lain belum tercatat.

| PR | Branch | Merge commit | Waktu merge WIB | Merged by | Review |
|---|---|---|---|---|---|
| [#1](https://github.com/BOGAGOL/juara1onno/pull/1) | feat/service-app | `20e08f39bffe` | 2026-10-27T14:10:28+07:00 | favianzhafif26 | tidak tercatat |
| [#2](https://github.com/BOGAGOL/juara1onno/pull/2) | feat/crypto-migration | `324caa9bfff9` | 2026-10-27T21:48:20+07:00 | albyarto | tidak tercatat |
| [#3](https://github.com/BOGAGOL/juara1onno/pull/3) | feat/crypto-migration | `0360af8a556a` | 2026-10-27T22:49:03+07:00 | albyarto | tidak tercatat |
| [#4](https://github.com/BOGAGOL/juara1onno/pull/4) | feat/crypto-migration | `5ab5248f499b` | 2026-10-27T23:44:32+07:00 | albyarto | tidak tercatat |
| [#5](https://github.com/BOGAGOL/juara1onno/pull/5) | feat/crypto-migration | `b8e999815f20` | 2026-10-28T01:10:13+07:00 | albyarto | tidak tercatat |
| [#6](https://github.com/BOGAGOL/juara1onno/pull/6) | feat/service-app | `ed88ecde7110` | 2026-10-28T10:18:27+07:00 | favianzhafif26 | tidak tercatat |

## Scan secret (C2)

gitleaks tidak tersedia. Regex: private-key header, token GitHub/Bao, credential URL dan assignment secret literal. Inventaris tree main: tidak ada .env/private-key/credential XML/init-material ter-track. Nilai kandidat tidak dicetak.

| Scope | File berubah | Added lines | Hasil |
|---|---:|---:|---|
| A_unmerged (origin/main → origin/feat/crypto-migration) | 39 | 479 | 0 kandidat,0 secret aktif terkonfirmasi |
| B_unmerged (origin/main → origin/feat/service-app) | 0 | 0 | 0 kandidat,0 secret aktif terkonfirmasi |
| A_merged_PR2_to5 (324caa9^1 → b8e9998) | 203 | 13558 | 0 kandidat,0 secret aktif terkonfirmasi |
| B_merged_PR1_and6 (20e08f3^1 → 9029b77) | 368 | 50835 | 4 kandidat,0 secret aktif terkonfirmasi |

Diff tiga-titik A/B kosong. Dua-titik A39 file adalah perbedaan tree historis, bukan pending merge. Range merged tambahan mencakup inherited team changes, bukan semuanya ditulis A/B. Kandidat: README interpolation, random synthetic UI fixture, dua URL test C. Tidak memindai seluruh history/log, jadi tidak menyimpulkan S05 global lulus. Kunci test vector sintetis dan dataset panitia PRIVATE dibedakan dari kredensial aktif.

## Turunkan menjadi Rencana bila belum selesai sebelum 20:00

- **A1: Pemulihan HTTP service end-to-end dari backup** — Rencana; restore DB/ACL/RLS/dekripsi sampel tetap tercatat Diimplementasikan+Diuji.
- **A5,B4: Analyst aggregate-only end-to-end dan kelompok<5 sepenuhnya tidak tampil** — Rencana untuk gap SQL/label; suppression jumlah HTTP yang diuji dicatat terpisah.
- **B3,B5: App protected target migrasi dan full authorized parity** — Rencana; disposable real crypto dan policy mock bukan target migrasi.
- **B6: Benchmark API resmi tujuh skenario dan rollback aman** — Rencana/BELUM DIUJI; hasil DB tidak menggantikan API.
- **A7,B7: Paket deploy server terpadu final** — Rencana; runbook/launcher lokal TLS/HTTPS memiliki bukti dengan scope terbatas.
- **A8,B8: Draf bab laporan A/B tersedia** — Rencana; pemilik menulis draf, README tidak dianggap bab.

Tidak ada benchmark B-P-P-B dijalankan atau dijadwalkan. Main dan branch A/B tidak diubah. Hanya JSON dan Markdown audit ini di-commit/push ke run/overnight-28okt.
