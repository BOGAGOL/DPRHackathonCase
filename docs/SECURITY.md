# Model ancaman dan keterbatasan

Tujuan kontrol adalah mengurangi nilai salinan data yang bocor dan menjaga fungsi
pengguna sah. Pengujian mencakup salinan dump/backup serta akses aplikasi yang
diizinkan; bukan eksploitasi jaringan atau jaminan seluruh host aman.

## Rancangan perlindungan

- 29 kolom sumber dipertahankan: 21 PII dan 4 FIN dienkripsi AES-256-GCM. Empat REF
  tersimpan plaintext; age_band diturunkan menjadi kelompok usia 10 tahun.
- DEK 32 byte terpisah per record/domain, nonce acak 12 byte. AAD mengikat tabel,
  kolom, UUID record dan versi. Gagal autentikasi menghasilkan error tanpa fallback.
- DEK disimpan wrapped oleh `pii-kek`/`finance-kek` di OpenBao. `search-hmac` mendukung
  blind index pada no_ktp, email dan pengguna. Nol awal identifier dipertahankan.
- TLS terverifikasi pada browser/API, PostgreSQL dan OpenBao; password akun Argon2id.
- Backend memutuskan izin per field/record sebelum serialisasi. Session cookie
  HttpOnly/Secure/SameSite Strict, CSRF, CSP nonce dan no-store membatasi paparan web.
- Analyst hanya membaca lima marginal agregat dengan count≥5. Kelompok kecil tidak
  menghasilkan label/baris. Role aplikasi, analis, auditor, backup dan administrasi
  database mempunyai hak berbeda; runtime tidak memakai root OpenBao/DBA.

## Skenario ancaman

| Ancaman | Kontrol | Batas |
|---|---|---|
| Dump dicuri tanpa kunci | Field AEAD dan envelope per record | REF, NULL, ukuran dan equality tetap terlihat |
| Backup dicuri/diubah | Enkripsi stream, manifest HMAC, SHA256 dan autentikasi sebelum restore | Kunci backup/HMAC harus disimpan terpisah; restore SQL hanya dari produsen tepercaya |
| Ciphertext ditukar/diubah | Tag GCM dan AAD record/kolom/versi | Tidak mencegah aplikasi terkompromi memakai kemampuan decrypt sah |
| Pengguna membuka record/field lain | Predicate backend, assignment dan RLS | Salah assignment administratif tetap risiko |
| Analis mengenali kelompok kecil | Penolakan raw table/view, suppression marginal | Bukan differential privacy atau jaminan kombinasi atribut/antarwaktu |
| Pencurian kredensial app_user | Least privilege dan NOBYPASSRLS | Setting app.principal bisa diganti; RLS bukan batas tunggal |
| Kebocoran kemampuan salah satu domain | Pemisahan PII/FIN/search | svc-app runtime memiliki dua domain; backend tetap dipercaya |
| Kunci hilang | Material recovery dan prosedur custody | DR key plane lintas mesin/HA belum dibuktikan lengkap |

## Analisis data dan prioritas

Inventaris dan klasifikasi tersedia pada [CSV](data/inventory-report.csv), matriks
risiko pada [CSV](data/risk-matrix.csv). Contoh dalam inventaris adalah pola pengganti,
bukan nilai sumber. Skor adalah assessment kondisi awal, bukan sisa risiko kuantitatif.
Ground truth 29 kolom berada di `scanner/ground_truth_eval.csv`; 26 pribadi dan 3
nilai institusi non-pribadi. Evaluasi scanner bersifat in-sample; kode_bank tetap
dienkripsi FIN karena hampir unik pada dataset, meskipun jenis nilainya institusional.

Prioritas: identitas/keuangan dan kredensial → enkripsi/masking/kunci → akses backend
serta TLS → backup/restore → pembuktian kebocoran dan biaya kinerja. Password di-hash,
nama tidak di-hash. Tidak ada kolom yang dihapus otomatis; minimisasi duplikasi nama
merupakan rekomendasi yang memerlukan keputusan pemilik data.

## Batas hasil

1. Data dan kemampuan decrypt yang dikuasai bersama tidak lagi menjamin kerahasiaan.
2. Blind index mengungkap equality/frequency dan mendukung dictionary attack jika
   search capability ikut bocor. REF/NULL serta legacy mapping masih terlihat.
3. Sumber/baseline plaintext dalam lab tidak dienkripsi oleh enkripsi field target.
   Uji dump logis bukan bukti perlindungan seluruh disk, WAL, swap atau crash dump.
4. Python/OS tidak menjamin zeroization seluruh salinan DEK; cache dibatasi TTL/ukuran.
5. Backup lama dapat memuat record yang kemudian dihapus sampai retensi berakhir.
   Retention deadline bukan scheduler purge atau bukti secure erase SSD.
6. Audit bukan log immutable yang tahan administrator OS/DB. Scan S06 operasional
   bersifat terbatas menurut path, encoding dan panjang nilai; bukan seluruh host.
7. S02 historis pada salinan API mencatat kegagalan analis. Uji 734 pada lingkungan
   berbeda tidak menggantikan hasil historis tersebut.
8. Bukti 734, 100k, 1M, lab native, browser deployment dan benchmark mempunyai scope
   berbeda. Pencapaian target kinerja belum terbukti; seri benchmark API belum lengkap.
9. Token workload berbatas TTL; unseal, pembaruan sertifikat, custody dan revokasi
   membutuhkan operator. Broker [refresh token opsional](TOKEN_REFRESH.md) memakai
   SecretID AppRole jangka panjang; pencurian RoleID dan SecretID memungkinkan
   penerbitan token svc-app sampai kredensial tersebut dicabut. TTL token tidak
   membatasi umur SecretID. OpenBao single node bukan arsitektur HA.
10. Inventaris dependency/audit tidak mencakup seluruh OS/image/CPython SSL; tag
    PostgreSQL18 belum mengunci digest. Lihat [dependency inventory](DEPENDENCIES.md).

Spesifikasi format v1 tetap pada `docs/contracts/CONTRACT.md` dan vector publik pada
`docs/contracts/test_vectors.json`. Kunci pada vector adalah material uji publik,
bukan kunci data runtime. Tidak ada perubahan format untuk merapikan dokumentasi.
