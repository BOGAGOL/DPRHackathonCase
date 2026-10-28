# Draf laporan teknis — Tim BOGAGOL

**Status: DRAF UNTUK REVIEW TIM.** Dokumen ini bahan sumber, bukan laporan PDF final.
Hasil yang belum tersedia ditandai jelas; ekspor PDF dilakukan setelah angka, sumber,
scope, atribusi dan persetujuan reviewer dilengkapi.

## Ringkasan

Prototipe ini mengurangi nilai salinan database melalui assessment per kolom,
enkripsi field terautentikasi, envelope key per record/domain, pencarian HMAC,
pembatasan akses, dan backup terenkripsi. Pertanyaan utamanya mencakup kerahasiaan
salinan data sekaligus keberlangsungan fungsi layanan dan pemulihan. PostgreSQL 18
dipilih dengan adaptasi dump sintetis panitia; pengujian membedakan scope komponen,
lab nyata, deployment dan benchmark. Fondasi serta integrasi memiliki bukti, sedangkan
perbandingan kinerja protected/API, seluruh leakage artefak dan beberapa aspek DR
masih perlu dilengkapi dari pekerjaan tim. Klaim dibatasi oleh bukti yang dirujuk.

## 1. Masalah, data dan prioritas

Dump sintetis panitia menggambarkan profil anggota: identitas, alamat, kontak,
rekening dan atribut keluarga. Salinan plaintext membuka informasi tanpa perlu
mengeksploitasi aplikasi. Dataset sumber berisi 734 baris dan 29 kolom eksplisit,
tanpa DDL/PK/FK; tim membentuk schema baseline PostgreSQL, menjaga nol awal identifier
dan aturan NULL, kemudian menghasilkan target protected baru. `legacy_row_id`
menjaga pelacakan validasi, sedangkan identitas protected memakai UUIDv4.

Prioritas ditentukan oleh sifat/kegunaan data, pola identifier, kemungkinan keterkaitan,
kebutuhan pencarian, dan dampak domain. Data keuangan dipisahkan dari PII; kode_bank
ikut diproteksi karena dapat menjadi proxy identitas pada sumber. Tiga kolom nama
identik dicatat sebagai peluang minimisasi, tetapi kontrak migrasi mempertahankan
semua kolom. Analisis bukan sekadar mematuhi nama/komentar tabel.

Diagram pada [arsitektur](../architecture/README.md) dan [threat model](../security/THREAT_MODEL.md)
menjelaskan batas data/app/key-plane. Risiko residual tidak disembunyikan oleh istilah
"enkripsi database" atau "data leak-proof".

## 2. Tantangan 1 — penemuan dan klasifikasi

Scanner semiotomatis menggabungkan struktur, nama, isi, pola, kamus, teks bebas,
statistik dan relasi/atribut turunan. Inventory mencakup lokasi, pola termasking,
tipe, kelas, risiko, alasan, rekomendasi, kebutuhan akses dan pencarian. Hasil mesin
perlu direview manusia; klasifikasi bukan keputusan hukum otomatis.

Acuan evaluasi 29 kolom dijelaskan secara terpisah; surrogate id tidak dimasukkan
sebagai atribut sumber. Evaluasi raw scanner 1.2 mencatat precision 0,96296, recall
1,0 dan F1 0,98113 (TP26/FP1/FN0/TN2), dengan label **in-sample**. Uji nama kolom
disamarkan tersedia; generalisasi ke database lain tidak disimpulkan dari satu tabel.
Review akhir kelas ambigu dan matriks risiko masih perlu disahkan tim. Bukti E01/E02.

## 3. Tantangan 2 — nilai data ketika bocor

Setiap record mempunyai DEK PII dan FIN yang berbeda. Nilai sensitif memakai
AES-256-GCM dengan nonce acak dan AAD yang mengikat tabel, kolom, UUID serta versi.
DEK dibungkus Transit OpenBao; tabel tidak menyimpan DEK plaintext. Exact lookup
no_ktp/email/pengguna memakai HMAC sesuai normalisasi kontrak, tanpa hash tanpa kunci
untuk identifier berentropi rendah. REF dan age_band dipertahankan untuk fungsi agregat.

Pengujian kripto membuktikan round-trip, tamper/swap fail-closed dan format bersama.
Namun ini belum menggantikan simulasi artefak kebocoran. Tim perlu memasukkan hasil
dump tanpa kunci, capability PII/FIN/search, backup tanpa key, dan residual inference
dari pekerjaan C yang direview. **Status hasil ESCE/DIE/ELS/DBR final pada snapshot
ini: BELUM LENGKAP.** Jangan menulis 0% leakage seluruh data hanya dari adanya AEAD.

Blind index membocorkan equality/frequency; REF dan NULL tetap terlihat. Capability
search dapat mendukung dictionary attack, sedangkan aplikasi dengan kemampuan
decrypt yang dikuasai bersama tidak lagi dijamin rahasia. Bukti E02/E03, rencana di
[indeks evidence](../evidence_index.md).

## 4. Tantangan 3 — at rest, in transit, in use

At rest: field sensitif pada protected dienkripsi, backup di-stream ke enkripsi
terpisah dengan manifest HMAC. Source/baseline plaintext, metadata, log, file fisik
dan WAL mempunyai batas berbeda. Tidak ada klaim full-disk encryption atau bahwa
salinan seluruh instance lab tidak mengandung plaintext.

In transit: browser/frontend/API menggunakan HTTPS; API-PostgreSQL verify-full
dengan CA; OpenBao TLS dan CA eksplisit. CA/hostname salah diuji pada lab. Baseline
benchmark mempunyai pengecualian non-TLS terbatas agar kondisi awal tetap setara,
bukan konfigurasi yang berlaku pada protected/restore atau aplikasi produksi.

In use: backend memeriksa peran, scope record dan field, mendekripsi yang diperlukan,
melakukan masking dan merilis DTO minimal. DEK/cache dibatasi TTL/ukuran, tetapi
zeroization seluruh salinan Python/OS tidak dijamin. Kunci dan data dipisahkan
secara kewenangan, bukan otomatis tahan administrator OS yang berkuasa.

Unseal manual, token policy TTL, revokasi migrasi dan rotasi tersedia. Rotasi lab
Alby membuktikan seluruh 100.734 wrapper PII akhirnya versi target v2 dengan nilai
tetap; tidak menetapkan versi semua VM. DR key-plane lintas mesin masih rencana.

## 5. Tantangan 4 — backend dan frontend

Service App menyediakan enam peran dengan autentikasi Argon2id, secure/httpOnly/
SameSite cookie, CSRF, validasi, parameterisasi, role minimum dan audit metadata.
Frontend tidak memutuskan hak atas nilai lengkap yang disembunyikan; backend memakai
allowlist DTO dan masking. Browser storage dan raw JSON diperiksa pada scope pengujian.

RLS pada protected memakai principal transaksi dan access_scope. Pencuri credential
app_user dapat mengganti setting principal, sehingga RLS bukan pengganti otorisasi.
Analyst tidak mendapat raw table/view: analyst_summary merilis lima marginal dengan
count>=5, tanpa label kelompok kecil. Filter cohort lama ditolak dan total API null.
Suppression marginal bukan differential privacy atau k-anonymity gabungan.

Acceptance setelah A5 mencatat 143 pemeriksaan pada lab 17 record buatan sendiri
dengan PostgreSQL/OpenBao TLS, backend/frontend dan Chrome nyata setelah restore.
Deployment web diuji 100 pemeriksaan menggunakan enam akun, tanpa SSH atau mutasi
anggota. Identitas commit dan konfigurasi SQL/TLS internal VM tidak diklaim terinspeksi
langsung. Bukti E09–E12 menjelaskan pembatasannya.

## 6. Tantangan 5 — metode dan hasil pengujian

Pisahkan eksperimen DB dan API, gunakan dataset/hardware/workload sebanding,
minimal tiga pengulangan, raw yang dipertahankan, median antar-run, serta target
yang ditetapkan sebelum eksperimen. Ukur p50/p95, throughput, error, CPU/RAM, storage
dan backup/restore, termasuk biaya crypto dan komunikasi yang dilindungi.

| Bagian | Hasil yang tersedia | Status |
|---|---|---|
| Scanner | E01, evaluasi in-sample | TERUJI dengan batas |
| Kripto/migrasi | E03–E06, format dan all-rows validation sesuai laporan | TERUJI sesuai dataset/laptop |
| Backup/restore | E07/E10, integritas, dua mode, cutover aplikasi lab | TERUJI sesuai scope |
| Akses/browser | E09–E12 | TERUJI sesuai scope |
| Baseline awal | E13, DB plain 100k/1m | TERUJI; bukan perbandingan after |
| Protected/API official comparison | Belum lengkap pada snapshot | BELUM DIUJI/LENGKAPI |
| Leakage semua capability/artefak | Pekerjaan C belum tergabung lengkap | PARSIAL |

**Tabel angka kinerja final belum diisi.** Ambil hanya dari hasil before/after yang
direview bersama raw, commit, dataset, konfigurasi, jumlah run dan status target.
Hasil gagal tetap dilaporkan; jangan melonggarkan target setelah melihat hasil.

## 7. Tantangan 6 — penerapan bertahap dan recovery

Urutan penerapan: assessment dan review profile; TLS/key-plane/least privilege;
baseline; migrasi target baru; validasi; akun/scope dan acceptance; cutover;
backup/restore; retensi/rotasi/audit; pengukuran ulang. Prasyarat/resource,
rollback dan pekerjaan kustodian ada di [operasional](../operations/OPERATIONS.md).

Restore memverifikasi manifest/digest/frame sebelum membuat DB baru. Tanpa akses
OpenBao field tetap ciphertext; dengan capability sah aplikasi dapat dipulihkan
sesuai marker/role/RLS/TLS. Backup lama tetap memuat data yang kemudian dihapus
sampai retensinya selesai. Kehilangan backup key/HMAC atau key-plane dapat membuat
data tidak terbuka, sehingga escrow dan drill lintas mesin harus direncanakan.

Kebutuhan biaya/resource belum diekstrapolasi ke produksi. Instansi perlu menghitung
compute, storage/WAL, salinan backup/restore, latensi Transit, kustodian dan waktu
pemulihan berdasarkan beban nyata. Tidak ada angka rupiah yang dikarang di sini.

## 8. Keterbatasan, simpulan dan lampiran

Lihat [daftar keterbatasan](../security/LIMITATIONS.md). Prototipe mempunyai fondasi
dan bukti komponen/integrasi, tetapi keberhasilan komprehensif harus dibatasi oleh
scope dan pekerjaan yang belum selesai. Nilai inovasi terletak pada assessment
yang mengendalikan perlindungan, pemisahan blast radius, dan bukti yang bisa ditinjau,
bukan klaim "kebocoran tidak mungkin berarti apa-apa" tanpa batas.

Lampiran: inventory/ground truth, matriks risiko, kontrak/vector, evidence index,
diagram/threat model, runbook reproduksi/recovery, SBOM/atribusi, pernyataan AI dan
manifest paket. Finalisasi sumber, caption/angka, reviewer, PDF dan slide sesuai
[checklist](../submission/CHECKLIST.md). Referensi utama ada di [SOURCES](../submission/SOURCES.md).
