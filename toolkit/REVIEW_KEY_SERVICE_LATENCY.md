# Review Alby: perf/keyservice-latency

Perubahan ini diminta Delf untuk diagnosis overhead OpenBao. Belum di-merge ke main;
review Modul A diperlukan sebelum integrasi. Ciphertext v1, AAD, bidx, normalisasi,
policy, format wrapped DEK, dan konfigurasi TLS tidak berubah.

Pengukuran awal 200 panggilan/komponen pada concurrency 1 dan 8 direkam di
`evidence/benchmark/keyservice_diagnosis.json`, sebelum perubahan runtime.
HTTPX sudah menggunakan client/pool persisten per worker; trace terukur tidak
menemukan TCP connect atau TLS handshake baru. Pada concurrency 8, HMAC mean
19,60 ms, unwrap 20,72 ms, datakey wrapped 23,18 ms; dekripsi satu field lokal
0,029 ms. Ini menunjukkan biaya jalur RPC/concurrency, bukan bukti handshake
berulang atau CPU kriptografi server yang jenuh. Sampling CPU mikro bersifat singkat;
resource sesi naive 60 detik juga dipertahankan untuk konteks.

Perubahan toolkit yang perlu direview:

- `https_pool.py` + jalur `request_bytes` pada `openbao.py`: session HTTPS
  persisten berbasis `http.client.HTTPSConnection`, pool maksimal8, idle expiry60s,
  SSLContext CA/hostname/TLS minimum1.2 yang sama. Mengurangi dispatch/per-request
  overhead HTTPX/httpcore; kedua transport sebelumnya dan sekarang sama-sama
  memakai keep-alive. Bukan klaim bahwa handshake dihilangkan dari setiap request.
  Respons dibaca utuh (maksimum4 MiB), koneksi gagal dibuang, tidak retry, tidak
  mengikuti redirect, target origin tetap, error tanpa body/secret. Tidak ada
  perubahan algoritme kripto atau format pesan Transit. Default `https_pool`;
  `DPR_OPENBAO_HTTP_TRANSPORT=httpx` mempertahankan transport lama untuk pembanding.
  `connection_stats()` hanya mengekspos counter agregat.
- `openbao.py`: batas eksplisit delapan koneksi/keep-alive dan idle expiry 60 detik.
  Verifikasi CA, hostname, TLS minimum 1.2, larangan proxy/redirect, identitas/token,
  serta fail closed tetap. Pool sebelumnya sudah ada; perubahan ini tidak diklaim
  sebagai penyelesaian utama latensi selama beban kontinu. Perbaikan final berasal
  dari jalur session yang lebih ringan di atas, bukan sekadar mengganti batas pool.
- `bidx.py`: `BlindIndexer.digests` menggabungkan maksimal 100 pasangan kolom/nilai
  melalui satu HMAC batch, dengan pesan domain v1 yang sama. NULL tidak dikirim;
  urutan, versi, ukuran hasil dan kegagalan atomik divalidasi. Insert benchmark
  memakai satu batch tiga kolom, sebelumnya tiga RPC.
- `keys.py`: hanya menambah statistik agregat hit/miss/batch pada cache DEK yang
  sudah ada. Tidak menambah cache plaintext, KEK, search key, atau file cache.

Benchmark default **cache mati**. Opsi `DPR_BENCH_DEK_CACHE_TTL=60` memakai cache
DEK yang sudah diuji di KeyManager, maksimum `DPR_BENCH_DEK_CACHE_ENTRIES=4096`
per worker (8 worker = maksimum 32768 entri, terpisah per koneksi). TTL tidak
diperpanjang oleh cache hit, dibatasi juga oleh kedaluwarsa token; pergantian scope,
kegagalan unwrap dan close membersihkan cache, dengan pengosongan bytearray best
effort. TTL membatasi pemakaian; penghapusan entri expired dilakukan lazy pada
unwrap berikutnya atau close, sehingga bukan jaminan semua byte hilang dari RAM
tepat pada detik ke-60. Memori proses memegang DEK, dan revokasi jarak jauh pada
jalur cache hit tidak selalu diketahui langsung: maksimum sisa TTL cache 60 detik.
KeyManager default toolkit yang dipakai konsumen lain tidak diubah.

Korpus benchmark hanya 2048 profil; hit rate dan varian cache mati wajib ditampilkan.
Tidak ada kesimpulan kelulusan target dari smoke. B-P-P-B resmi ulang belum dimulai.
Perkiraan ulang satu pasangan varian pada kedua skala: sekitar 2 jam 20 menit waktu
ukur/orchestrasi seperti naive_v1, atau 2,5 jam dengan verifikasi. Mengukur cache
mati dan aktif sebagai dua eksperimen lengkap membutuhkan sekitar 5 jam.

Reproduksi memakai env kredensial yang sudah dimuat sesuai README, tanpa menaruh
nilai secret pada argumen/history:

```powershell
python -m pytest toolkit/tests benchmark/tests -q
python -m benchmark.keyservice_verify parity
python -m benchmark.keyservice_verify leak
python -m benchmark.keyservice_verify smoke
```

Verifikasi final transport baru disimpan terpisah dari cohort HTTPX awal:

```powershell
python -m benchmark.keyservice_transport_probe
python -m benchmark.keyservice_verify parity --session https_pool_v2
# Gate no-key final menunjuk scan penuh yang sama: codec/profile/dump tidak berubah.
python -m benchmark.keyservice_verify smoke --session https_pool_v2
```

Probe API penuh sesudah perbaikan: c8 mean HMAC HTTPX9,56 ms versus pool4,56 ms,
200 panggilan/kasus. CA yang tidak dipercaya ditolak oleh koneksi nyata. Implementasi
memakai API standar http.client, tanpa patch private internals atau perubahan
jadwal thread/GIL. Transport lama dan baru tidak menjanjikan jumlah TLS write yang
sama; tidak ada klaim coalescing header/body sebagai alasan hasil.

Driver smoke menjalankan dua pengukuran 30 detik per varian, concurrency 8,
warmup 10 detik, urutan plain/off/on/on/off/plain. Hasil, hit rate yang tidak
menghitung warmup, dan status AC ada di `evidence/benchmark/keyservice_latency/`.
Raw smoke tetap di `results/bench/keyservice_smoke/`; hasil naive tidak dihapus.


### Hasil verifikasi final https_pool_v2

Test toolkit+benchmark180 PASS/1 SKIP disposable; test vector PASS. Parity final16.000 request pada dua skala dan dua konfigurasi cache,0 mismatch; kedua probe tulis rollback PASS. No-key scan penuh100k/1M ESCE0%, dipakai ulang sesudah perubahan transport dengan alasan dan fingerprint yang dicatat. Integritas akhir kelima DB cocok terhadap naive_v1: count/checksum/sequence/logical ciphertext tetap; principal dan scope kembali ke count awal. Audit setup/cleanup tetap disimpan.

| Varian final (100k,read_by_nik) | p50 ms | p95 ms | Mean ms | req/s | DEK hit rate |
|---|---:|---:|---:|---:|---:|
| plain | 3.595 | 6.774 | 3.901 | 2038.26 | 0.00% |
| protected_cache_off | 29.056 | 43.447 | 30.229 | 264.27 | 0.00% |
| protected_cache_60 | 33.072 | 60.255 | 34.722 | 230.14 | 49.57% |

Seluruh12 smoke (cohort HTTPX awal dan pool final) nol error; tidak ada run dibuang. Final AC/Kernel-Power qualified sepanjang sesi. Pool final tidak membuka koneksi TLS baru dalam jendela terukur; delapan koneksi sudah hangat sebelum measurement. HTTPX tetap opsi pembanding, tidak dipilih otomatis saat gagal.

Rekomendasi final: pool HTTPS baru + HMAC batch, **cache DEK benchmark tetap OFF**. Cache dievaluasi, tetapi p95 memburuk pada kedua cohort; jangan mengklaim cache menyelesaikan overhead. Hit rate hanya statistik lookup DEK, tidak menghitung warmup. Korpus2048 dan total40s per run menguntungkan cache; TTL60s belum kedaluwarsa dalam smoke. P95 protected tetap di atas ambang rasio/absolut terhadap plain dalam smoke; target tidak diubah, tidak ada klaim kelulusan resmi.

Evidence ringkas evidence/benchmark/keyservice_latency/verification.json; cohort final https_pool_v2/smoke.json; seluruh hasil awal tetap ada. Tidak memulai B-P-P-B ulang; sediakan2,5 jam satu varian,5 jam untuk dua eksperimen cache-off/on penuh.
