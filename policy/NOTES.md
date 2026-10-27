# Tahap 3: Assessment-Driven Protection Profile

`protection_profile.yaml` dibuat oleh `python -m policy.build_profile`, bukan diedit
manual. Urutannya: inventory scanner -> kandidat tindakan -> keputusan eksplisit
di `overrides.yaml` -> validasi kontrak bagian 3 -> profile. Ketidaksesuaian
inventory/override/kontrak menggagalkan build. Penerapan skema membangun ulang
profile dan menolak profile yang sudah tidak sesuai inputnya.

Inventory default adalah `evidence/scanner/before_v1/inventory.csv`: hasil scanner
734 baris yang tersedia di Git. Direktori `results/scanner/` tidak tersedia di
checkout ini. Inventory lain bisa diberikan melalui `--inventory`, misalnya:

```powershell
.\.venv\Scripts\python.exe -m policy.build_profile --inventory results/scanner/run/inventory.csv
.\.venv\Scripts\python.exe -m pytest policy/tests -q
```

Gunakan path inventory di dalam repo agar penerapan bisa memverifikasi kembali
provenance. Evidence build berada di `evidence/policy/build-profile.json`.
SHA-256 ketiga input tercatat; output deterministik dan tidak menyertakan contoh
nilai, `sample_masked`, atau alasan bebas dari inventory.

Keputusan v1: 29 kolom sumber selain `id`; 25 AEAD (21 PII, 4 FIN), 4 REF,
3 blind index (`no_ktp`, `email`, `pengguna`). Ada 12 perubahan tindakan terhadap
rekomendasi scanner; keputusan akhirnya selalu mematuhi kontrak. Kolom nama
turunan tetap ada walau scanner mengusulkan delete; `kode_bank` masuk FIN;
rekomendasi blind index tambahan tidak diterapkan. Alasan dan penilaian scanner
tersedia per kolom. `id` menjadi `legacy_row_id`; identifier aplikasi UUIDv4 acak.

Asumsi turunan `age_band`: interval 10 tahun, tanggal acuan tetap **2026-10-01**,
selaras `datagen.REFERENCE_DATE`, bukan tanggal saat migrasi dijalankan. Tanggal
lahir sumber tetap AEAD; NULL tetap NULL. Implementasi derivasi dan validasi
tanggal dilakukan pada tahap migrasi. Kontrak v1 dan normalisasi bidx tidak berubah.

Batas bukti tahap ini: inventory yang dipakai masih assessment sumber 734,
bukan hasil scan protected/100k. Profile bukan bukti bahwa migrasi telah berjalan
atau sisa REF telah memenuhi k-anonymity; pengujian tersebut milik Modul C.
Fixture `synthetic_scope_fixture.json` berlabel `test_only` dan seluruh principal,
UUID, serta username dibuat untuk test. Fixture hanya dimuat di PostgreSQL
sementara oleh integration test, tidak otomatis masuk database development.

Sinkronisasi main 27 Oktober 2026 (`20e08f3`): kontrak menambahkan pengecualian
dataset panitia pada repo private. Profile dibangun ulang agar hash provenance
kontrak sesuai versi terbaru; keputusan perlindungan/format v1 tidak berubah.
Dataset lokal sama dengan file yang kini dilacak di main. Pengecualian dataset
tidak berlaku bagi credential, kunci, log, atau artefak hasil migrasi.
