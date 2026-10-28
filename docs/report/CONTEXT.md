# Konteks penulisan laporan

Pakai bersama [draf](DRAFT.md), [indeks evidence](../evidence_index.md),
[checklist](../submission/CHECKLIST.md) dan [sumber](../submission/SOURCES.md).
Tujuannya menyediakan fakta dan struktur; bukan menghasilkan klaim yang belum diuji.

## Identitas dan pertanyaan penelitian

Tim BOGAGOL: Alby (A: data/crypto/infra), Zhafif (B: Service App), Delf (C: scanner,
datagen, benchmark/verifikasi dan koordinasi laporan). Judul kerja:
**Pelindungan Data Pribadi Berbasis Assessment ketika Salinan Database Bocor**.
Pertanyaan: apa yang tetap dapat dibaca/disimpulkan dari salinan data, dan apakah
layanan yang sah tetap benar, cukup cepat, dan dapat dipulihkan?

Ini prototipe hackathon dengan dataset sintetis, bukan sistem resmi DPR RI atau
klaim kepatuhan/keamanan produksi. PostgreSQL dibolehkan soal; adaptasi dump perlu dijelaskan.

## Fakta data dan adaptasi

- Input panitia: 734 INSERT, satu tabel, 29 kolom eksplisit, tanpa CREATE TABLE/PK/FK.
- `no_ktp` pada data contoh 14 digit, bukan NIK standar 16; jangan menyebut validasi NIK nasional.
- Nama/nama_lengkap/nama_tanpa_gelar identik pada 734 sumber; tidak dihapus pada migrasi.
- 367 tanggal_pernikahan NULL; pola NULL termasuk leakage yang diterima.
- `id` dibuat untuk baseline sebagai surrogate; bukan kolom asli dalam denominator evaluasi.
- PostgreSQL 18 di pg-dpr:5433. Source postgres/baseline_100k/baseline_1m dijaga;
  target protected baru dan UUIDv4 dipetakan dari legacy_row_id.
- Pembesaran data seed 42 menjaga aturan/keterkaitan yang didefinisikan datagen;
  ukur 100k dan 1m secara terpisah bila hasilnya diklaim.

Verifikasi konteks melalui [metodologi ground truth](../ground_truth_methodology.md),
schema/validasi SQL dan evidence migrasi; jangan menyalin nilai anggota ke laporan.

## Keputusan teknis yang tidak boleh berubah saat menulis

| Aspek | Fakta |
|---|---|
| Field crypto | AES-256-GCM, nonce acak 12 byte, blob 0x01 + nonce + ciphertext/tag16 |
| AAD | `dpr\|v1\|anggota_protected\|<kolom>\|<UUID lowercase>\|<protection_version>` |
| Envelope | DEK PII + FIN baru per record, 32 byte; hanya wrapped DEK di DB |
| KEK | OpenBao Transit pii-kek/finance-kek; HMAC search-hmac |
| bidx | no_ktp/email/pengguna; keyed HMAC-SHA256 32 byte; normalisasi persis kontrak |
| Domain | 25 kolom AEAD, 4 REF asli + age_band turunan; kode_bank masuk FIN |
| NULL | Sumber NULL tetap NULL, bukan enkripsi string kosong |
| Analyst | View marginal security_barrier, HAVING count>=5; total API null; cohort filter ditolak |
| Auth | Argon2id, enam peran, scope record/field, CSRF, secure cookies, no-store, CSP |
| DB | schema_owner NOLOGIN, app_user NOBYPASSRLS, minimum grants dan RLS SET LOCAL |
| Transit AAD | Desain tidak bergantung associated_data Transit; AAD field diverifikasi lokal |
| Backup | pg_dump stdout langsung ke framed GCM, manifest HMAC key terpisah, DB restore baru |

Format lengkap ada di [kontrak](../contracts/CONTRACT.md), bukan tabel ringkasan ini.
Masking tidak sama dengan enkripsi. KEY operator/DBA terpisah secara kewenangan,
tetapi kompromi seluruh OS/data/key-plane tetap di luar jaminan kerahasiaan.

## Angka yang tersedia dan cara mengutip

- Scanner raw 1.2 in-sample: precision 0,96296; recall 1,0; F1 0,98113;
  TP26/FP1/FN0/TN2 pada 29 kolom. Review manusia belum boleh dianggap selesai.
- Migrasi 734 dan 100k mempunyai all-rows/all-fields validation sesuai E04/E05.
- Rotasi lab Alby: PII v1→2, keseluruhan 100.734 wrapper akhirnya versi target;
  percobaan sempat terhenti/resume. Versi Bao fresh VM dapat berbeda.
- E10: 143 pemeriksaan lab 17 invented rows dengan restore + HTTPS + Chrome.
- E11: 100 pemeriksaan enam akun deployed web; bukan inspeksi langsung SQL/TLS internal VM.
- Baseline100k/1m ada, protected/API official comparison belum lengkap pada snapshot.
  Jangan mengisi p95/throughput after atau ESCE tanpa bukti hasil nyata.

Jumlah test bukan ukuran akurasi/keamanan universal. Cantumkan commit/waktu/scope
di caption, dan tautkan ke E01–E15. Jangan menggabungkan beberapa laptop menjadi satu eksperimen.

## Kerangka yang disarankan

Ringkasan; masalah dan threat model; data/adaptasi; T1 assessment; T2 pengurangan nilai
kebocoran; T3 at-rest/transit/in-use; T4 aplikasi; T5 metode+hasil keamanan/kinerja;
T6 penerapan/rollback/operasional/resource; keterbatasan; simpulan; referensi/lampiran.
Tidak ada kewajiban 40–70 halaman pada PDF soal; target internal itu bukan syarat panitia.

## Aturan untuk penulis/agen lanjutan

1. Jangan mengarang benchmark after, leakage metric, halaman buku, reviewer atau hasil VM.
2. Labeli Diimplementasikan+Diuji / Diimplementasikan / Rencana, dengan evidence dan batasnya.
3. Pisahkan hasil unit/mock, lab nyata, deployment web, dataset tim, serta benchmark resmi.
4. Tidak ada plaintext anggota, token, key, share, cookie, credential URL atau dump dalam lampiran.
5. Tulis alasan REF, bidx equality, residual k, RLS spoof, backup lama dan source plaintext secara jujur.
6. Jangan menjadikan dokumen prototype lama/branch belum digabung sebagai bukti current snapshot.
7. Tim manusia mengesahkan kelas/risiko dan final PDF/slide; ekspor tidak sama dengan pengesahan.
