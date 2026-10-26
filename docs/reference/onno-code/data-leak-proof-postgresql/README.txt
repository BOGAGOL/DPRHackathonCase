DATA LEAK-PROOF POSTGRESQL LAB
==============================

Kode pendamping buku:
Onno W. Purbo, Data Leak-Proof: Teknik Proteksi Data di PostgreSQL
agar Kebocoran Tidak Berarti Apa-Apa, 2026.

Komponen:
- PostgreSQL 18
- OpenBao Transit
- Prometheus, node_exporter, postgres_exporter, Grafana
- Python 3: Faker, AES-GCM, HMAC blind index, migrator
- pgbench dan benchmark bisnis
- backup, restore, rotasi, plaintext scan, dan runbook

PERINGATAN
----------
Paket ini dibuat untuk laboratorium lokal dengan data sintetis. Jangan gunakan
password, token, kunci, atau konfigurasi contoh di produksi. Sebagian perintah
dapat memerlukan penyesuaian terhadap versi image, sistem operasi, TLS,
jaringan, dan kebijakan organisasi. Siapkan debugging, rollback, dan bukti
backup-restore sebelum perubahan produksi.

QUICK START
-----------
1. Salin .env.example menjadi .env.
2. Ganti seluruh nilai CHANGE_ME dan buat dua kunci berbeda:
     openssl rand -base64 32
     openssl rand -base64 32
3. Validasi:
     make check
4. Jalankan:
     make up
5. Inisialisasi dan unseal OpenBao secara manual:
     make openbao-init
6. Instal toolkit Python:
     make venv
7. Jalankan unit test:
     make test

PostgreSQL: 127.0.0.1:5432
OpenBao:    http://127.0.0.1:8200
Prometheus: http://127.0.0.1:9090
Grafana:    http://127.0.0.1:3000

TLS tidak diaktifkan pada quick-start satu-host. Contoh konfigurasi TLS ada
di config/postgres dan runbooks/go-live.txt. Produksi wajib menggunakan TLS,
secret manager, penyimpanan OpenBao yang tahan gagal, dan image yang dipin ke
versi patch atau digest yang telah diuji.

