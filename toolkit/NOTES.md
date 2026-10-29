# Modul A — Tahap 2 toolkit kripto

## Keputusan implementasi

- Paket `dprcrypto` di toolkit/, install editable atau wheel. Tidak mengubah
  kode aplikasi B, scanner C, data asli, atau kontrak. Menambah test_vectors.json
  sesuai instruksi pengguna/kontrak bagian 9 (key contoh publik khusus test).
- Codec baru mengikuti binary v1 persis: 01 + nonce CSPRNG 12 byte + CT/tag16.
  Referensi buku memakai JSON dan AAD tenant/table/column/id serta UUIDv5;
  tidak diadopsi karena kontrak menetapkan binary, prefix dpr|v1 dan UUIDv4.
  Protection version integer positif smallint termasuk di AAD. Key 32 byte.
- NULL berbeda dengan empty string. Tidak ada konversi tanggal/angka/normalisasi
  plaintext secara diam-diam. Caller menyiapkan string ISO/desimal.
  Decode gagal, blob pendek/versi salah, AAD/key salah, tamper, dan UTF-8 invalid
  semuanya DecryptionError generik; tidak ada fallback/default plaintext.
- DEK lokal CSPRNG baru per record/domain, lalu Transit encrypt pii-kek/finance-kek.
  Ini bekerja dengan svc-migration tanpa decrypt; datakey/wrapped saja tidak
  memberi plaintext DEK yang dibutuhkan untuk AES lokal. DEK tidak ditulis ke DB.
- Client workload terpisah dari bootstrap admin infra. Token hanya dari env,
  lookup-self memeriksa tepat satu policy yang dikenal dan TTL terbatas <=4 jam;
  root/default/multi-policy dan token tak terbatas ditolak. Tidak ada auto-renew.
  Identitas env bisa diganti tanpa membangun ulang client. HTTPS origin + CA env,
  hostname verification, TLS >=1.2, tanpa proxy env/redirect. Tidak ada HTTP retry
  atau fallback, response body dan kredensial tidak masuk exception/log.
- Context pada referensi adalah derivasi key, bukan AAD. Dukungan opsional wrap
  memakai associated_data base64. Field AEAD tetap lokal; tidak bergantung AAD
  Transit. Request utama wrap DEK tidak perlu context/associated_data.
- Batch unwrap memakai batch_input + reference indeks non-PII, cek jumlah/urutan,
  panjang DEK dan error per item, menolak seluruh page/chunk bila ada kegagalan.
  Maksimum 100 item/request, duplikat didedup, urutan keluaran asli dipertahankan.
- Cache LRU thread-safe: default 15 s/256 entri; maksimum 60 s/4096. Scope key
  service+identitas token+KEK+wrapped DEK. Hit tidak memperpanjang lease, expiry
  dibatasi expiry token, pergantian/invalidasi identitas membersihkan cache.
  Semua chunk ditampung di memori dan divalidasi sebelum commit ke cache.
- HMAC dipilih remote /transit/hmac/search-hmac/sha2-256 agar search key tidak
  diekspor. Input tepat kontrak; output base64 pada vault:vN:... didekode 32 byte,
  bukan disimpan sebagai teks/prefix. Domain separation lewat label kolom dalam
  pesan sesuai bagian 7, bukan KDF lain yang mengubah bidx. Normalisasi tidak
  mengikuti casefold/NFKC referensi; email hanya strip+lower. NIK ASCII digit.
- HMAC pin default versi 1, bukan latest. Svc app/migration memberi hasil sama.
  Rotasi search-hmac tidak mengubah lookup lama sampai rebuild bidx terkoordinasi.
- Masking memenuhi contoh panitia dan menyembunyikan identifier pendek. Tidak
  menambahkan hak akses. Keputusan domain FIN/otorisasi tetap tugas pemanggil.

## Batas yang diterima

- CSPRNG nonce 96-bit bersifat probabilistik; sampel nonce berbeda bukan bukti
  matematis bebas collision selamanya. Per-record/domain DEK membatasi pemakaian.
- Revokasi server baru diketahui saat request berikutnya. Cache hit bisa memakai
  lease yang tersisa (maksimum TTL cache); pemanggil harus clear() saat revokasi/
  insiden atau matikan cache untuk kebutuhan revokasi segera. Token expiry lokal
  selalu diperiksa. Cache hit saat outage dapat bekerja selama lease masih sah.
- Penimpaan bytearray cache best effort; Python/library/caller dapat menyisakan
  salinan immutable. Jangan mengklaim secure zeroization atau perlindungan dari
  kompromi proses yang sedang menguasai DEK dan plaintext.
  Expiry diterapkan saat akses; penghapusan entri expired lazy pada operasi
  berikutnya/clear/close. TTL bukan jaminan pemusnahan fisik semua salinan key.
- RecordKeys/WrappedDEK tidak menampilkan DEK pada repr. Caller tetap dilarang
  log/serialize object internal. Public fixture adalah satu-satunya material
  contoh yang sengaja disimpan, tanpa memakai kredensial/data produksi.
- Blind index masih membocorkan kesetaraan/frekuensi; metadata NULL tetap terlihat.
- Backend lama menggunakan format berbeda dan harus diintegrasikan Modul B.
  Tidak ada migrasi data, query DB, profile, atau backup baru pada tahap ini.

## Sumber primer

- [Cryptography AESGCM 46.0.5](https://cryptography.io/en/46.0.5/hazmat/primitives/aead/)
- [HTTPX SSL context](https://www.python-httpx.org/advanced/ssl/)
- [OpenBao 2.5.5 batch decrypt](https://github.com/openbao/openbao/blob/v2.5.5/builtin/logical/transit/path_decrypt.go)
- [OpenBao 2.5.5 HMAC format/key_version](https://github.com/openbao/openbao/blob/v2.5.5/builtin/logical/transit/path_hmac.go)

## Pengujian

Lihat README untuk perintah reproduksi; semua data sintetis. Evidence status saja
di evidence/crypto/. Integrasi memakai OpenBao 2.5.5 disposable, tidak mengakses
PostgreSQL atau container lab utama.

Hasil akhir 26 Oktober 2026:

- Toolkit: **85 test lulus**, termasuk integrasi TLS OpenBao nyata (84 unit +
  1 integrasi). Gabungan aplikasi + infra + toolkit: **150 lulus, 1 skip** dataset
  panitia, 1 warning deprecation Starlette milik dependensi aplikasi lama.
  `evidence/crypto/regression-tests.xml` memuat hasil run gabungan tersebut.
- `evidence/crypto/integration.json`: **24 pemeriksaan lulus** pada OpenBao
  2.5.5. 50 record, 100 DEK domain unik, 1 batch PII + 1 batch FIN, cache hit tanpa
  request baru, mixed batch gagal seluruhnya, root/role tanpa decrypt ditolak,
  invalidasi scope saat ganti token, lookup HMAC tetap setelah rotasi versi,
  wrapped DEK versi lama tetap bisa dibuka, CA salah/outage uncached ditolak.
- `evidence/crypto/vectors.json`: **8 pemeriksaan lulus**, enam field vectors
  (termasuk Unicode, tanggal, leading zero, empty dan NULL) dan lima bidx vectors.
  SHA-256 fixture dicatat untuk mengikat evidence ke vector yang sama.
- `evidence/crypto/packaging.json`: wheel hanya berisi paket runtime, tanpa
  test/fixture/private key. Import dan AEAD round-trip berhasil dari direktori
  sementara di luar repo, dengan interpreter isolated (-I).
- Test toolkit memakai namespace paket agar conftest/nama modul tidak berbenturan
  dengan suite aplikasi/infra. Perintah gabungan di README sudah diuji langsung.
- Re-run infra disposable juga lulus 60 pemeriksaan; hanya timestamp evidence
  infra diperbarui. Tidak ada perubahan konfigurasi/implementasi Tahap 1.
- Semua container/volume uji disposable dibersihkan. Tidak menjalankan migrasi
  atau query ke database asli/baseline. Tahap 1 telah di-merge fast-forward ke
  main (392b1ac) atas instruksi pengguna; Tahap 2 di branch feat/crypto-toolkit.


## 28 Oktober 2026 ? usulan perf/keyservice-latency untuk review Alby

Atas instruksi Delf, branch ini menambahkan batas pool HTTP eksplisit, API HMAC batch lintas kolom dengan format v1 tetap, dan statistik agregat cache DEK yang sudah ada. Cache default toolkit tidak diubah; benchmark menyediakan varian cache-off dan opt-in TTL60. Tidak mengubah policy, key material, TLS verify, ciphertext, AAD atau bidx. Diagnosis membuktikan koneksi lama sudah persisten; tidak mengklaim handshake per request. Lihat REVIEW_KEY_SERVICE_LATENCY.md dan evidence/benchmark/keyservice_diagnosis.json; jangan merge sebelum review Modul A.
