# 5. Angka, bukti dan spesifikasi visual

## Sumber fakta

Basis penulisan adalah konteks laporan/evidence yang sudah disiapkan pada branch
submission, bukan angka hasil benchmark baru. Snapshot laporan memuat hasil kode
dan sesi historis berbeda. source_manifest.json mengikat sumber paket presentasi;
commit paket bukan otomatis commit kode yang diukur pada eksperimen.

| ID | Angka/fakta yang dapat dipakai | Sumber dan batas |
|---|---|---|
| K01 | Sumber 734 record/29 kolom, target 100k/1M | Kontrak/profile/validation; data panitia sintetis, tidak ada nilai lengkap di slide |
| K02 | Scanner precision 96,30%, recall 100%, F1 98,11%; regex recall 42,31% | B03;29 label, in-sample, raw sebelum pengesahan manusia |
| K03 |21 PII+4 FIN=25 AEAD;4 REF;3 bidx | B01/B05; field counter bukan jumlah seluruh kolom DB |
| K04 | AES-256-GCM, nonce 12 byte, DEK 32 byte/record/domain, AAD | B01/B06; format v1, fail closed, bukan seluruh disk/WAL |
| K05 | No-key ESCE 0% pada 100k/1M | B22; denominator 2.449.994/24.500.005 sel AEAD non-NULL |
| K06 | PII~83,67%, FIN~16,33%, search~12,24%; k sumber 734=1 | B22/B23; FIN/search dapat identifier, kamus lengkap sintetis, proyeksi residual 1–3 atribut |
| K07 | SQLA5 31 checks, ambang 5 | B11; fixture SQL terisolasi, bukan semua VM |
| K08 |143 checks/17 record buatan tim | B12; layanan+restore+TLS+Chrome nyata, bukan benchmark dataset |
| K09 |100 checks/enam akun web; operator VM reset 65 smoke terpisah | B13/B14; bukan 243 checks satu lingkungan, bukan full pentest |
| K10 | DB v2 NIK 1M p95 B 6,0637/P 38,6237 ms; throughput 2260,0568/293,6117 rps | B18; median 4 run/mode,8 worker,60 s ukur,cache OFF; P01/P01A/P02 FAIL, P03 PASS |
| K11 | Naive→v2 protected NIK 1M 78,9665→38,6237 ms (~51,09% turun) | B17/B18; antarsesi, bukan kelulusan target/isolasi sebab tunggal |
| K12 | API PLANNED, scenarios kosong | B20; rencana 2 ulangan/mode <minimum 3, GET only, tidak ada hasil ukur |
| K13 | Storage 1M 825.194.175→2.210.617.023 byte(~2,679×) | B08; snapshot, bukan ukuran konstan setelah WAL/workload berubah |
| K14 | Rotasi 100.734 wrapper PII v1 → v2; backup protected 100k 11,376413s/restore 16,415305s | B09/B10; lab Alby/operasional single result, bukan median 3 run atau rotasi seluruh 1M/VM |

Angka lengkap, scope dan locator ada di evidence_cards.json dan CSV tables/.
Sertakan minimal ID/scenario/skala/unit/ulangan pada grafik, dan sumber detail di
speaker notes. Angka DB yang dipilih pada slide hanyalah contoh, bukan ringkasan
semua skenario terbaik. Semua 14 kombinasi skala×skenario pada naive/v2 gagal target
latensi/throughput, error lulus. Jangan menghilangkan hasil gagal pada footnote.

### Kode sumber B dan slide cadangan A

K01–K14 adalah kartu klaim lokal. A01–A06 adalah **slide cadangan**, sedangkan
kode B berikut diwarisi dari peta evidence laporan. Jangan menyamakan keduanya.

| Kode sumber | Arti dan locator repo |
|---|---|
| B01/B05/B06 | Kontrak/profile/kripto: docs/contracts/CONTRACT.md, policy/protection_profile.yaml, evidence/crypto/ |
| B03 | Scanner: evidence/scanner/evaluation_v1_2.json dan evaluation_regex_only.json |
| B07/B08 | Migrasi/storage: evidence/migration/validation-protected_*.json dan evidence/overnight/migration_1m/completion.json |
| B09/B10 | Backup/rotasi: evidence/backup/ dan evidence/keys/rotation.json |
| B11/B12 | SQL A5/lab recovery: evidence/access-control/analyst_suppression.json dan evidence/backup/service-recovery-integration.json |
| B13/B14/B15 | Web/VM/policy aplikasi: evidence/acceptance/deployed-browser.json, app/evidence/access-control/vm-pentest-summary.json, app/backend/service_app/ |
| B17/B18 | DB naive/v2: evidence/benchmark/bppb_compare.json dan bppb_v2_compare.json |
| B20/B21 | API/target: evidence/benchmark/api_bppb_compare.json dan docs/targets.md |
| B22/B23 | Leakage/residual: evidence/leakage/after_summary.json dan protected_{100k,1m}/residual_after.json |
| B24/B26 | TLS/runtime: infra/NOTES.md, infra/postgres/, app/deploy/ dan scripts/deploy/ |

Path ini untuk provenance, bukan instruksi membuka seluruh repo saat presentasi.
Data terpilih dan batasnya sudah berada pada evidence_cards.json; gunakan kartu K
dan CSV lokal untuk membuat grafik, lalu taruh locator sumber di notes.

## C01 — Pemulihan nilai AEAD tanpa kunci

Data: tables/chart-no-key.csv. Bar 0–100% dimulai nol, dua kelompok 100k/1M,
baseline 100 dan protected 0. Tulis denominator dalam notes; sumbu “ESCE 25 field AEAD
non-NULL (%)”. Beri label 0 agar bar nol tetap terbaca. Caption menyatakan tidak
menghitung REF/metadata/inferensi. Hindari ikon perisai “100% aman”.

## C02 — Latensi lookup NIK pada DB v2

Data: tables/chart-db-nik.csv. Dua kelompok 100k/1M, setiap kelompok baseline dan
protected. Sumbu p95 ms dimulai nol; gunakan 1M pada slide utama, dua skala di backup.
Tampilkan p95 median 4 run, bukan mean atau pooled p95. Boleh tampilkan garis target
P01 berupa 1,5× B masing-masing skala, **bukan satu batas global**. P01A terpisah.

## C03 — Throughput lookup NIK pada DB v2

Data: tabel yang sama dengan C02, kolom throughput_rps. Grafik terpisah dari
latensi karena unit/arah baik berbeda. Batas P02=70% baseline per skala. Protected
berada di bawahnya; jangan memotong sumbu sehingga penurunan tampak kecil.
Caption “DB adapter; bukan HTTP request benchmark” menjelaskan unit operasi.

## C04 — Perbaikan naive dibanding v2

Data: tables/chart-optimization.csv. Bandingkan hanya p95 protected NIK dalam
dua sesi yang dinyatakan. Tulis sekitar51% lebih rendah dan bahwa target masih
gagal; bukan “performa naik51%” tanpa metrik atau “51%lebihaman”. Koneksi lama
sudah keep-alive; perbaikan transport tidak dibuktikan hanya dari handshake.

## C05 — Capability dan residual

Data: tables/leakage.csv, ESCE 25 AEAD dalam%. Kelompok baseline/no-key/PII/FIN/search
per skala. Jangan membuat stackedbar total capability: nilai bisa overlap dan
search merekonstruksi lewat oracle, bukan AES decrypt. DIE 100% pada PII/FIN/search
harus dijelaskan bila diagram menimbulkan kesan FIN tidak mengungkap identitas.
Residual k=1source734 adalah hasil berbeda, bukan persentase ESCE.

## C06 — Biaya penyimpanan

Data: tables/chart-storage.csv, byte atau GiB dengan konversi 1024^3 yang dinyatakan.
Bandingkan skala yang sama dan beri waktu/scope snapshot. Bukan overhead murni
AES: tuple/index/metadata/wrapper ikut memengaruhi ukuran. Jangan memakai rasio
2,679× untuk meramalkan biaya produksi tanpa pengukuran baru.

## Aset dan keterbacaan

assets/ berisi diagram arsitektur PNG/SVG/Mermaid yang disalin dari bahan laporan.
Tidak ada logo resmi, foto dekoratif, screenshot aplikasi atau video yang dibuat
pada tugas konteks ini. Jika deck dibuat, diagram/grafik harus tetap tajam dan
bisa diedit bila relevan. Gunakan satu komposisi yang mudah dibaca, bukan grid
panel kecil. Tulis judul singkat, maksimal tiga pesan utama per slide kecuali
roadmap yang berisi lima tahap. Jangan mengecilkan font untuk memasukkan matriks
29 kolom atau JSON mentah; pindahkan ke backup/lampiran.

Kode MIT, dokumentasi orisinal CC BY-NC4.0, dataset panitia khusus kompetisi dan privat.
Di slide referensi, sebut dua dokumen panitia, buku Onno dengan edisi/bab yang
terverifikasi, kontrak proyek, PostgreSQL 18, OpenBao 2.5.5 dan library AEAD. Jangan
mengarang halaman buku atau menyatakan seluruh kode rujukan karya tim.
