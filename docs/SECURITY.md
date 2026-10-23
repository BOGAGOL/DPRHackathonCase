# Model ancaman dan batas bukti

| Ancaman | Kontrol dan bukti | Batas |
|---|---|---|
| Dump DB dicuri tanpa key | AES-GCM per field, dump canary/key scan | Nama/ruangan/ID/metadata tetap terlihat |
| Record ID diganti | Scope assignment di query dan PATCH, tes API/browser | Tidak memakai PostgreSQL RLS; aplikasi adalah boundary otorisasi |
| Operator mengambil field lain | DTO allowlist, masking server | Operator yang boleh menulis bisa memasukkan nilai baru; bukan izin membaca penuh |
| Admin membaca data | Tidak ada implicit sensitive grants/assignments | Admin permission manager bisa sengaja mengotorisasi staff; dual control belum ada |
| SQL injection | SQLAlchemy bound params, allowlist sorting, escaped wildcard | Tes payload bukan bukti semua kelas injection mustahil |
| XSS | React text rendering, validasi kontak, CSP dasar, Chromium payload test | CSP script masih unsafe-inline untuk Next runtime; nonce CSP belum diterapkan |
| CSRF/session theft | HttpOnly, SameSite Strict, origin check, bound CSRF, expiration/revoke | Secure cookie hanya saat HTTPS; development memakai HTTP loopback |
| Ciphertext ditukar/diubah | GCM tag + AAD record/field, key/tamper/AAD tests | Tidak mengikat revision anti-replay; DBA dapat mengembalikan ciphertext lama pada field yang sama |
| KMS gagal | Adapter fail closed, mock outage test | Live Transit, rotation, token expiry belum diuji |
| Log/backup leak | Audit metadata, access log off, hide SQL params, independently encrypted dump | Audit bukan tamper-proof; volume/WAL encryption belum aktif |
| Key + DB kompromi | Pemisahan secret dan database | Siapa yang menguasai aplikasi dan key dapat mendekripsi; tidak ada klaim zero-knowledge |

At rest: 27 field dienkripsi, NULL dipertahankan, secret tidak ada di DB/source, logical dump dan encrypted backup drill diuji. File fisik DB/WAL/temp belum dienkripsi oleh proyek; bergantung pada host encryption yang harus dikonfigurasi dan dibuktikan tersendiri. Backup recovery key lokal harus dipisahkan sebelum deployment.

In transit: HTTP/loopback PostgreSQL di lab lokal. Adapter Transit memerlukan HTTPS verified. HTTPS example disertakan, tetapi sertifikat browser/API/PostgreSQL/Transit live adalah **NOT TESTED**. Tidak mengklaim TLS hanya karena ada Caddyfile.

In use: dekripsi berdasarkan allowlist backend, query record scope sebelum DTO, no-store API, tidak menyimpan access token di localStorage. Plaintext di memori Python dan browser staff yang berizin tetap ada selama penggunaan; memory wiping tidak dijamin. Nullability, panjang ciphertext dan kesamaan HMAC tetap membocorkan metadata.

Rate limit terikat process, login peer+username hashed dan KTP lookup per actor. Cocok untuk satu worker demo; gunakan limiter terpusat/edge sebelum multi-worker/multi-instance. Proxy client IP belum dipercaya secara eksplisit: login peer dapat sama untuk semua pengguna melalui Next.js, sehingga batas IP konservatif dapat memengaruhi beberapa pengguna sekaligus.

Runtime app DB role dapat membaca password hashes (dibutuhkan autentikasi), memodifikasi user/assignment sesuai kebutuhan administrative endpoints, dan INSERT audit. Tidak SUPERUSER/CREATEDB/CREATEROLE/BYPASSRLS, tidak bisa DDL/member delete/audit update. SQL injection dengan identitas app tetap berbahaya bagi ciphertext, hashes dan integritas. Role analyst/auditor/backup terpisah, RLS, WORM/remote audit sink dan MFA belum diprovisioning; backup tooling lab memakai owner dan harus diganti identity backup khusus di deployment.

Tes menggunakan data sintetis dan lingkungan lokal. 33 tes Python mencakup policy/API/crypto/parser/backup/configuration, ditambah Chromium dan PostgreSQL evidence. Secret scan membandingkan secret aktif terhadap file yang tidak di-ignore, bukan scanner seluruh riwayat Git atau seluruh jenis secret. Dependency manifests dipin; audit CVE/supply-chain dan penetration testing eksternal belum dilakukan. Jangan menyatakan production-ready atau patuh UU PDP hanya karena tes lulus.
