# Target verifikasi dan benchmark Modul C

Tanggal penetapan: **26 Oktober 2026 WIB** · Pemilik: **Delf / Modul C** · Branch: `feat/verify-bench`.

Amandemen dataset: **27 Oktober 2026 WIB**. **Perubahan dataset: arahan technical meeting panitia, 27 Okt 2026; disetujui tim.**
Dataset utama menjadi `baseline_1m`; `baseline_100k` tetap sebagai titik skala dan jaring pengaman.
Hasil baseline awal 100k yang sudah diterima tetap dipertahankan sebagai sesi tersendiri.
Seluruh ambang fungsional, keamanan, dan kinerja tetap; amandemen ini tidak mengubah nilai target.

**Status: disetujui tim sebelum benchmark; belum merupakan hasil pengujian.** Semua angka di bawah
adalah target, bukan hasil. Persetujuan mencakup ambang cadangan level DB dan nama asli ground truth.
Benchmark baru boleh berjalan setelah dokumen ini beserta berkas yang diminta di-commit dan di-push,
serta hash/waktu commit dilaporkan.
Hash commit penetapan dicatat di metadata pengujian; jangan mengisi dokumen ini dengan hash dirinya sendiri.

Acuan: [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) bagian 3–4, 6–10;
[CONTRACT.md](contracts/CONTRACT.md);
[PROMPT_C_VERIFY_EVIDENCE.md](ai-prompts/PROMPT_C_VERIFY_EVIDENCE.md) bagian 6;
[PROMPT_CODEX_DATAGEN_BENCHMARK.md](ai-prompts/PROMPT_CODEX_DATAGEN_BENCHMARK.md).
Kontrak format/kewenangan tetap berlaku. Target tidak boleh dilonggarkan berdasarkan hasil pengujian;
perubahan memerlukan persetujuan tim, commit baru, dan pengujian ulang yang dinyatakan terpisah.

## 1. Lingkungan, data, dan batas pengujian

- Windows PowerShell, Docker Desktop, PostgreSQL **18**, container `pg-dpr`, `127.0.0.1:5433`.
  Bandingkan PostgreSQL plaintext dengan PostgreSQL protected pada perangkat dan konfigurasi yang sama.
- Database `postgres.public.anggota` berisi **734 baris sumber** dan hanya dibaca. Jangan menjalankan DDL,
  DML, atau restore pada database tersebut. Dataset utama dibuat pada **database baru `baseline_1m`**,
  total **1.000.000 baris = 734 sumber + 999.266 tambahan sintetis**, seed **42**.
  **`baseline_100k` tetap dipertahankan**, total **100.000 = 734 sumber + 99.266 tambahan sintetis**,
  seed **42**, sebagai titik skala dan jaring pengaman; tidak dibuat ulang atau ditimpa.
- Validasi melaporkan dua kelompok secara terpisah: kesamaan 29 kolom/NULL/nol awal pada 734 sumber,
  serta format/relasi/distribusi/anomali pada tambahan sintetis. Keunikan identifier diperiksa pada
  seluruh baseline. Anomali sumber dipertahankan dan tambahan mengikuti proporsi sumber yang diukur.
- Datagen boleh memakai admin `postgres` container untuk lab. Workload baseline memakai **`bench_user`**,
  akses hanya database baseline yang ditetapkan (`baseline_1m` dan `baseline_100k`), tanpa superuser/DDL;
  beri hak minimum SELECT/INSERT/UPDATE dan penggunaan
  identity yang diperlukan. Setelah baseline jadi, **`scanner_user`** mendapat SELECT di sana.
  Koneksi admin untuk membuat/restore DB dipisahkan dari koneksi workload.
- `protected_100k`/`protected_734`, toolkit, profile, role protected, dan backup produksi dikerjakan A;
  Service App dan matriks akses dikerjakan B. Migrasi menunggu konfirmasi baseline C sudah terekam.
  Perbandingan utama 1M harus memakai salinan protected dengan populasi 1M yang sama dari A;
  hasil 100k dilaporkan terpisah dan tidak dipakai sebagai pasangan before/after untuk 1M.
  Seluruh database eksperimen berada di instance `pg-dpr` yang sama; OpenBao memakai compose A.
- `age_band`: usia tahun penuh terhadap **2026-10-01**, lalu kelompok **10 tahun**: usia 20–29 →
  `20-29`, 30–39 → `30-39`, dan seterusnya. Hitung sebelum/sesudah ulang tahun pada tanggal acuan;
  tanggal lahir NULL menghasilkan NULL. Tanggal invalid/masa depan dicatat sebagai kesalahan validasi,
  bukan diam-diam dikonversi menjadi kelompok usia.

## 2. Target fungsional dan pemulihan

Persentase lulus = jumlah kasus yang memenuhi hasil yang diharapkan / jumlah kasus wajib yang dijalankan.
Kasus wajib yang belum dijalankan tidak memenuhi target. Hasil yang sah diperiksa secara semantik,
termasuk isi field yang diizinkan, masking, NULL, nol awal, dan identitas record; bukan sekadar HTTP 200.

| ID | Target | Cara membuktikan |
| --- | --- | --- |
| F01 | **100% validasi dataset lulus** | Count utama 1.000.000 (734 sumber + 999.266 sintetis), seed 42; titik skala/jaring pengaman 100.000 tetap valid; 734 sumber tidak berubah; keunikan global; determinisme seed, format/relasi, dan pelaporan distribusi/anomali sesuai prompt datagen. |
| F02 | **100% fungsi pengguna sah lulus** | Tujuh workload bisnis dan endpoint wajib B; hasil plain/protected setara sesuai role, termasuk pencarian, paging, update dan insert. |
| F03 | **100% validasi migrasi lulus** | Count dan decrypt-and-compare seluruh kolom/record, NULL, blind index/normalisasi, idempotensi; kumpulkan evidence A. Tidak menghapus kolom sumber. |
| F04 | **100% restore berhasil** | Baseline minimal 3 backup/restore ke DB sementara, count sama; protected memakai drill A: integritas, ciphertext tetap terlindungi tanpa akses decrypt, dan layanan/data pulih dengan kredensial sah. |
| F05 | **Data terhapus tidak muncul di backup baru** | Uji retensi/deletion A pada salinan lab terpisah; backup baru tidak memuat record terhapus. Catat bahwa backup lama masih dapat memuatnya hingga retensi habis. |

## 3. Target keamanan

| ID | Target | Cakupan penerimaan |
| --- | --- | --- |
| S01 | **100% akses ilegal ditolak** | Matriks role × endpoint × record × field; IDOR/BOLA; analyst hanya proyeksi/agregat, auditor hanya audit. Periksa JSON mentah dan browser/storage, bukan tampilan saja. |
| S02 | **100% pembatasan role DB yang diwajibkan lulus** | Analyst ditolak membaca tabel dasar, backup ditolak UPDATE, auditor ditolak membaca anggota, app ditolak DDL; flag/grant/RLS sesuai kontrak. `bench_user` dibatasi pada baseline dan `scanner_user` hanya baca. |
| S03 | **ESCE = 0% untuk kolom AEAD pada dump tanpa kunci** | `protected_dump_no_key`: 0 sel AEAD non-NULL pulih persis / total sel AEAD non-NULL yang diperiksa. Laporkan juga ESCE seluruh sel sensitif; REF/metadata tidak dianggap terenkripsi. |
| S04 | **100% tamper/swap gagal didekripsi** | Ubah satu bit, tukar antar-record, tukar antar-kolom; harus gagal tertutup karena tag/AAD. Tidak ada fallback/default plaintext; kegagalan API generik dan diaudit tanpa nilai pribadi. |
| S05 | **0 secret aktif terdeteksi** | Repo dan riwayat Git, dump/backup/evidence/log; tidak ada password/token/DEK/KEK aktif. Fixture kripto sintetis kontrak diberi konteks dan tidak dihitung sebagai secret aktif. |
| S06 | **0 nilai pribadi plaintext pada keluaran operasional yang dipindai** | Log aplikasi/PostgreSQL general/slow/error, file temp, history, ekspor, dokumentasi/screenshot/evidence. Baseline dan known-values memang plaintext dalam lokasi privat yang ditentukan; path persis `sql/baseline/02_data.sql` dikecualikan sesuai CONTRACT bagian 11 dan `verify/scan_config.toml`; pengecualian dicatat. |
| S07 | **100% backup rusak ditolak integritasnya** | Tamper artefak/manifest pada salinan uji A gagal sebelum pemulihan dipakai. Backup protected tidak membuka data tanpa kredensial yang dibutuhkan. |
| S08 | **100% batas domain kripto yang diuji sesuai kontrak** | Policy finance hanya mendekripsi AEAD FIN; policy PII hanya AEAD PII; search key membuktikan kebocoran equality/dictionary, tidak mendekripsi AEAD. Tidak boleh mendekripsi domain AEAD lain. REF dan inferensi antar-kolom tetap dilaporkan. |
| S09 | **100% kasus kontrol aplikasi wajib B lulus** | Parameterisasi/SQL injection, validasi, autentikasi/sesi/CSRF, XSS, cookie/header/cache, minimisasi respons, kegagalan crypto; bukti TLS browser/API/DB/OpenBao diverifikasi terpisah dari benchmark. |

ESCE skenario umum = sel sensitif non-NULL yang dapat dipulihkan persis / total sel sensitif non-NULL.
Evidence harus menyimpan numerator, denominator, cakupan kolom/record, metode pemulihan dan skenario.
Skenario tanpa decrypt tidak boleh memakai token decrypt tersembunyi. Denominator kosong atau cakupan
tidak lengkap dinyatakan tidak tersedia/parsial; jangan disimpulkan 0% atau lulus penuh.

Simulasi meliputi `baseline_dump`, `protected_dump_no_key`, `protected_dump_with_pii_key`,
`protected_dump_with_finance_key`, `protected_dump_with_search_key`, `backup_artifact_no_key`.
Gunakan artefak nyata; dump custom diekstrak lewat `pg_restore` sebelum pemeriksaan SQL.
Pencurian file data/WAL perlu pengujian artefak fisik tersendiri; hasil dump logis tidak membuktikannya.

## 4. Target kinerja

Ambang berikut berlaku **per scenario API umum**, dengan endpoint/role/DTO dan parameter bisnis yang sama.
API umum mencakup list 50 anggota, detail, exact search NIK/email, update kontak, insert, dan mixed;
endpoint analytics/audit/auth dilaporkan terpisah bila diukur.

**Ambang P01–P03 yang sama juga berlaku pada benchmark level DB** (adapter plain versus protected)
sebagai target cadangan: p95 ≤ 1,5× baseline, throughput ≥ 70% baseline, dan error rate tidak naik.
Hitung dan laporkan penilaian **DB dan API secara terpisah**, per scenario pada level yang sama.
Jika API belum tersedia saat benchmark after, target API berstatus **BELUM DIUJI** dan target DB
tetap dinilai. Kelulusan DB tidak mengubah status API menjadi lulus.

| ID | Metrik dan target | Perhitungan |
| --- | --- | --- |
| P01 | **p95 protected ≤ 1,5 × baseline (API dan DB terpisah)** | Median p95 per-run protected / median p95 per-run plain ≤ 1,5. |
| P02 | **Throughput protected ≥ 70% baseline** | Median throughput sukses per-run protected / median throughput sukses per-run plain ≥ 0,70. |
| P03 | **Error rate tidak meningkat** | Median error rate per-run protected ≤ median error rate per-run plain, tanpa toleransi tambahan; baseline 0 berarti protected harus 0. |

Latency diukur dari pemanggilan operasi sampai hasil bisnis selesai diterima dan divalidasi, termasuk
biaya crypto/unwrap untuk protected. Throughput sukses = jumlah operasi berhasil / durasi pengukuran;
error rate = operasi gagal / seluruh operasi terukur. Timeout, exception, dan hasil bisnis salah
dihitung gagal. Penolakan yang memang diharapkan dalam security test dilaporkan di suite terpisah.
P95 untuk target dihitung dari seluruh operasi terukur, termasuk kegagalan; statistik operasi sukses
juga dilaporkan terpisah. Laporkan cakupan statistik sukses/gagal secara eksplisit.
Jika baseline pembagi nol, pengukuran tidak lengkap, atau kondisi tidak sebanding, hasil belum dapat dinilai.

Laporkan **p50/p95/p99/mean, throughput, error, CPU/RAM DB dan client, ukuran database/tabel/indeks,
waktu backup/restore, ukuran dump/backup**. CPU/RAM, storage, dan durasi backup/restore tidak mempunyai
ambang numerik tambahan pada penetapan ini; kewajibannya adalah pengukuran before/after yang lengkap.
Resource API/OpenBao dicatat jika tersedia dan batas pemantauannya dijelaskan.

## 5. Metode pengukuran yang ditetapkan sebelum run

1. Workload: `read_by_nik`, `read_by_email`, `read_profile`, `list_page` (50 record), `update_contact`,
   `insert_member`, `mixed` (**70% baca / 30% tulis**). Definisi/subkomposisi mixed, role dan field
   yang dikembalikan dibekukan di workload manifest sebelum run dan sama untuk plain/protected.
2. **Concurrency 8**, durasi **60 detik/run/scenario**, warmup **10 detik** di luar sampel terukur.
   Baseline awal: **3 run/scenario**; backup/restore baseline: **3 run**. Catat parameter aktual.
   Baseline awal 100k telah direkam terpisah di `evidence/benchmark/baseline/` dan dipertahankan.
   Datagen/validasi/snapshot 1M tidak menjalankan benchmark; benchmark 1M menunggu perintah terpisah.
3. Saat A/B siap, eksperimen perbandingan memakai **dua blok utuh B–P–P–B**, sehingga ada
   **4 run per mode/scenario** (memenuhi minimum 3). B = baseline, P = protected. Jangan menggabungkan
   baseline awal dengan eksperimen berpasangan tanpa memisahkan sesi dan kondisi lingkungannya.
4. Seed/kunci lookup/record bisnis ditetapkan sekali dan dipakai ulang; pemetaan identity baseline ke
   UUID protected menjaga record yang sama. Operasi tulis memakai rollback atau data uji khusus yang
   dipulihkan sebelum run berikutnya; periksa count/checksum agar workload tidak menggeser dataset.
5. Adapter DB plain/protected menghasilkan hasil bisnis setara; adapter API memakai kode aplikasi
   sama dalam `MODE=plain` dan `MODE=protected`, termasuk transport/auth/DTO yang setara. Jangan
   membandingkan SQL langsung dengan HTTP, atau hasil lama PG17 dengan pengukuran PG18.
6. Simpan setiap request (timestamp/scenario/latency/status tanpa parameter pribadi) dan sampel
   resource berkala. CPU/RAM container `pg-dpr` melalui Docker stats, client melalui psutil;
   resource yang gagal terkumpul dicatat tidak tersedia, bukan angka nol.
7. Ringkas setiap run lebih dulu, lalu **median antar-run** untuk setiap metrik/scenario; jangan
   mengganti dengan percentile gabungan seluruh run. Simpan raw dan ringkasan seluruh run,
   termasuk kegagalan. Alasan run invalid/retry dan hasil ulang harus terlacak.
8. Metadata: OS/CPU/RAM, Docker/PostgreSQL/Python dan versi dependensi, konfigurasi resource/cache,
   DB/count/seed/checksum/versi generator, workload/parameter, hash kode dan commit target, waktu UTC
   serta padanan WIB. Hindari mutasi pengguna/migrasi/beban lain selama sesi; catat gangguan.
9. Ukur dump custom/restore baseline ke DB sementara baru; verifikasi count sesudah restore.
   Pengukuran backup protected A mencatat biaya enkripsi/integritas secara jelas agar batasnya
   tidak disamakan dengan pg_dump baseline saja. Jangan restore menimpa sumber/baseline.

## 6. Scanner dan risiko residual yang wajib dilaporkan

- Evaluator memakai acuan Alby **29 kolom tanpa `id`**: `scanner/ground_truth_eval.csv` dan
  [ground_truth_methodology.md](ground_truth_methodology.md), tanpa mengubah isinya. Label map di
  evaluator langkah 4 menangani `PERSON_NAME`, `NATIONAL_ID`, dan label lain, `is_personal` 1/0,
  serta `non-pribadi` versus `non_pribadi`. `id` prediksi dicatat tidak berlabel, bukan denominator.
- Laporkan precision/recall/F1, confusion matrix, akurasi jenis/kelas, missing/unmapped labels,
  baseline regex-only dan uji nama kolom disamarkan. Tidak menetapkan ambang akurasi baru;
  hasil tetap in-sample dan label institusi non-pribadi tidak mengubah keputusan FIN `kode_bank`.
- **DIE** = baris dengan minimal satu identifier langsung terbuka / total baris; daftar identifier
  ditetapkan dalam metodologi sebelum simulasi. **ELS** melaporkan kolom deterministik, jumlah kelas
  equality dan kelas terbesar. **DBR** melaporkan domain/kolom yang pulih per policy bocor.
- K-anonymity menguji kombinasi **1–3 atribut** dari REF `jenis_kelamin`, `pekerjaan_terakhir`,
  `nama_kppn`, `nama_bank`, `age_band`, serta indikator NULL yang terlihat. Laporkan k minimum,
  jumlah/persentase baris unik, cakupan kombinasi dan batas komputasi; tidak mengekspor nilai grup.
  Bandingkan baseline pada populasi yang sama; angka acuan **730/734** untuk kombinasi
  tempat/tanggal lahir/jenis kelamin hanya berlaku pada subset sumber 734, bukan otomatis 100k atau 1M.
- Tidak menjanjikan k minimum tertentu, DIE global nol, atau ESCE global nol: REF, pola NULL,
  equality/frekuensi dan inferensi tetap mungkin terbuka. Kebocoran aplikasi beserta kemampuan
  decrypt dapat membuka data; laporkan batas tersebut bersama hasil fisik/TLS yang belum diuji.

## 7. Evidence, status hasil, dan urutan pelaksanaan

- Ringkasan kecil **JSON/CSV ke `evidence/<kategori>/` dan di-commit**: dataset, benchmark,
  backup-restore, scanner, leakage, access-control. Pertahankan file bersama yang diwajibkan prompt:
  `evidence/scanner/evaluation.json`, `evidence/access-control/db-roles.json`,
  `evidence/secrets-and-logs.json`, `evidence/summary.json`. SBOM ke `docs/sbom/`.
- Raw besar ke **`results/` lokal, tidak di-commit**. Known-values, daftar kunci lookup yang memuat
  nilai pribadi, snapshot/dump plaintext dan kunci hanya di **`C:\dev\dpr-private\`**, dibaca melalui
  env **`DPR_PRIVATE_DIR`**. Direktori privat tidak menjadi keluaran log/isi evidence.
  Pengecualian khusus dataset panitia `sql/baseline/02_data.sql` hanya di repo PRIVATE sesuai
  CONTRACT bagian 11; dilarang dipublikasikan dan dikeluarkan dari paket lampiran publik.
- Kredensial dari env, input password PowerShell melalui `Read-Host -AsSecureString`; tidak di kode,
  argumen proses/history, atau output. Evidence berisi agregat/ID uji, bukan nilai record/secret.
  Catat pengecualian scan `docs/reference/` sesuai kontrak; jangan mengklaim cakupan yang tidak dipindai.
- Setiap hasil memuat ID target, status, jumlah kasus/numerator/denominator, waktu, commit dan perintah
  reproduksi. Status penilaian: **LULUS / GAGAL / BELUM DIUJI / TIDAK DAPAT DINILAI**; status yang
  belum teruji tidak boleh dianggap lulus. Indeks klaim memakai **Diimplementasikan + Diuji /
  Diimplementasikan / Rencana** dan menautkan evidence.
- Kode/evidence benchmark lama dipertahankan sebagai historis; utilitas yang cocok dipakai ulang
  setelah diperiksa/test. Catat komponen yang diadaptasi dan hasil lama yang digantikan di
  `benchmark/NOTES.md` saat implementasi, tanpa menghapus file lama.
- Urutan: persetujuan/commit target → datagen → baseline 3 run + backup/restore → scanner/evaluasi →
  leakage/residual baseline → integrasi A/B, keamanan dan benchmark after. **Berhenti setelah setiap
  langkah** dengan ringkasan, hasil test dan perintah PowerShell verifikasi.
