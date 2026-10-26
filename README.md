# juara1onno

## Scanner

Scanner lokal semi-otomatis menemukan kandidat data pribadi melalui isi sampel,
nama kolom, kamus, bentuk nilai, teks bebas, dan relasi. Hasil wajib ditinjau
manusia. Seluruh implementasi, konfigurasi, dan pengujian ada di `scanner/`.
Tidak ada layanan klasifikasi eksternal. Koneksi memakai transaksi read-only;
dump SQL hanya diparse, tidak dieksekusi.

Gunakan Python 3.11+ dan GNU Make. Di PowerShell, instal dan aktifkan environment:

```powershell
python -m venv scanner/.venv
.\scanner\.venv\Scripts\Activate.ps1
make scanner-install
```

Administrator membuat role melalui `scanner/sql/scanner_role.sql` (sekali saja):

```powershell
psql -X -W -h 127.0.0.1 -p 5433 -U postgres -d postgres -f scanner/sql/scanner_role.sql
```

Skrip meminta password role lewat Python `getpass` yang ditangkap langsung ke
variabel psql `:'scanner_password'`. Aktifkan environment Python terlebih dahulu.
Jangan menaruh password di argumen, kode, atau riwayat
terminal. Audit hak `PUBLIC` terlebih dahulu: `NOINHERIT` tidak menghapus hak
`PUBLIC`. Skrip hanya memberi CONNECT, USAGE public, dan SELECT public.anggota;
tidak memberi akses otomatis ke tabel baru. Sesuaikan daftar GRANT untuk sumber
lain setelah ditinjau administrator. Panduan rinci dan pemeriksaan hak ada di
[scanner/NOTES.md](scanner/NOTES.md).

Isi kredensial hanya melalui environment `SCANNER_DATABASE_URL`. Contoh aman
berbasis prompt tanpa menuliskan password tersedia di NOTES. `.env` tidak dibaca
otomatis dan sudah diabaikan Git. Jalankan:

```powershell
make scanner-test
make scan LABEL=before
make scan-dump FILE=path/ke/dump.sql LABEL=before
python -m scanner files --file path/ke/aplikasi.log path/ke/ekspor.csv --label before --out results/scanner/files-before
```

Tanpa Make, gunakan `python -m pip install -r scanner/requirements.txt`,
`python -m pytest scanner/tests -q`, dan
`python -m scanner db --schema public --sample 1000 --label before --out results/scanner/before`.
Mode dump menggunakan `python -m scanner dump --file path/ke/dump.sql --label before --out results/scanner/dump-before`.
`--sample` membatasi sampel per tabel dan hasil teks per file (default 1000).
`--label after` memakai `environment_after.yaml`; label lain harus mempunyai
konfigurasi environment atau menentukan `--environment path.yaml`.
Tiga faktor lingkungan (volume, exposure, recovery) dalam contoh adalah asumsi
yang harus diverifikasi. Sensitivitas dan dampak per jenis diatur melalui
`scanner/config/impact.yaml` (opsional `--impact path.yaml`). Dengan faktor
before 3/5/5, skor minimum adalah 16 (P2); P3 membutuhkan faktor lingkungan
lebih rendah yang memang terverifikasi, seperti contoh after.

Setiap scan menghasilkan `inventory.csv`, `relations.json`, `k_anonymity.json`,
`run_meta.json`, dan `report.html` statis tanpa JS eksternal. `features.json`
menyimpan semua fitur agregat dan bukti negatif; mode files juga menghasilkan
`findings.csv` berisi file, nomor baris, jenis, dan nilai termasking. Hasil berada
di `results/` yang diabaikan Git. Semua sampel dimasking, termasuk pada laporan
HTML dan temuan relasi; nilai pengelompokan k-anonymity tidak dikeluarkan.

Arti kolom `inventory.csv`:

| Kolom | Arti |
| --- | --- |
| `table`, `column`, `data_type` | Sumber, nama kolom, tipe penyimpanan |
| `detected_type` | Kandidat jenis data berdasarkan sinyal gabungan |
| `pdp_class` | Kandidat umum, spesifik, atau non_pribadi |
| `risk_level` | rendah, sedang, tinggi, kritis, dari rentang prioritas |
| `priority`, `priority_score` | P0–P3 dan total enam faktor (6–30) |
| `f_sensitivity`, `f_impact` | Faktor 1–5 per jenis dari impact.yaml |
| `f_exploitability` | Faktor 1–5 dari bukti isi; kategori, operasional, dan hitungan keluarga bernilai 1 |
| `f_volume`, `f_exposure`, `f_recovery` | Faktor 1–5 dari konfigurasi lingkungan |
| `content_score`, `name_score`, `confidence` | Skor jenis terpilih; bobot default 80% isi + 20% nama |
| `triage` | auto_accept, needs_review, atau low_confidence; semuanya tetap dilaporkan |
| `derived_from` | Kandidat sumber duplikat/turunan, dipisahkan titik koma |
| `consistent_protection_with` | Kolom sumber yang membutuhkan perlakuan masking/akses konsisten |
| `sample_masked` | Maksimal tiga contoh termasking |
| `reason` | Alasan berbasis fitur, bukti negatif, dan pertanyaan retensi |
| `recommendation` | Turunan: review_minimization; nama publik: retain+mask_for_analyst; tanggal lahir: generalize_for_analyst; password: hash Argon2id; jenis lain: proteksi sesuai konteks |
| `allowed_roles`, `search_need` | Default konfigurasi untuk revisi manusia |

Agama dipetakan sebagai umum dan ditandai rawan diskriminasi; data keuangan
pribadi, kesehatan, biometrik, genetika, catatan kejahatan, dan data anak sebagai
spesifik, mengikuti [UU PDP Pasal 4](https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022).
Klasifikasi kandidat tidak menggantikan penilaian konteks oleh tim.

Salin `scanner/ground_truth.template.csv` ke `scanner/ground_truth.csv`, isi manual
oleh anggota tim, lalu jalankan `make scan-eval LABEL=before`. Evaluasi mengukur
precision/recall/F1 personal, akurasi jenis dan kelas, confusion matrix, serta
false positive/negative pada output mentah sebelum koreksi manusia. Bandingkan
dengan `--baseline regex_only` pada perintah db/dump/files dan direktori output
terpisah. `low_confidence` tetap dihitung sebagai kandidat personal kecuali
kelasnya `non_pribadi`; keputusan ini tercantum di hasil evaluasi.

Keterbatasan: relasi dan deteksi jenis memakai sampel; kamus dan heuristik dapat
keliru. Format/enkripsi tidak membuktikan anonimitas. k-anonymity memakai agregat
seluruh tabel database atau seluruh dump, terbatas kombinasi 1–3 kolom kandidat;
NULL dikelompokkan bersama. Mode teks bebas tidak mempunyai k-anonymity. Parser
mendukung literal INSERT MySQL/PostgreSQL dan COPY teks PostgreSQL; ekspresi SQL,
COPY CSV/biner, dump arsip, serta beberapa ekstensi dialect ditolak. Mode dump
menaruh plaintext sementara di disk lokal sebelum dihapus. Detail keputusan,
hasil pengujian, batasan, dan validasi database asli: [scanner/NOTES.md](scanner/NOTES.md).

Versi 1.1.0 mengenali NIK berpanjang tidak baku hanya dengan dukungan isi dan
kata kunci nama; tanpa konteks nama tetap kandidat identifier. Nama berkardinalitas
rendah menjadi kategori, tanggal pernikahan dibedakan dengan pola tanggal/NULL
bersyarat, dan hitungan keluarga tetap umum serta needs_review. ID integer
berurutan pada sampel menjadi kandidat kunci penghubung operasional. Sumber
functional dengan rasio unik non-NULL >0.9 dilaporkan terpisah pada
`near_unique_quasi_identifiers`. Report menyediakan tabel ringkas dan cetak A4
landscape; k-anonymity diurutkan 1–3 kolom, maksimal 15 kombinasi minimal di HTML,
sementara semua agregat tetap di JSON. Setiap run mencatat versi, ringkasan
perubahan, dan kebijakan prioritas yang dipakai. Simpan run v1.1 di folder baru
agar hasil `before_v1/` tetap dapat dibandingkan.
