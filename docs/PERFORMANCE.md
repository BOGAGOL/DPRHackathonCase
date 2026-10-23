# Pengukuran kinerja lokal

Workload: baca/tulis kontak 80/20, concurrency 1, seed 2026, 300 operasi per konfigurasi per pengulangan, tiga pengulangan dengan urutan bergantian dan 20 warmup reads. Output bisnis setara; ciphertext dikembalikan ke snapshot awal setelah mutasi. Angka berikut adalah median, raw per-operasi tersedia di JSON.

Target development ditetapkan di runner sebelum pengujian: p95 < 100 ms dan zero unexpected errors. Workload kecil ini tidak membuktikan kapasitas produksi. CPU/RAM PostgreSQL mencakup process tree cluster native, termasuk background/idle backend; sum working sets dapat menghitung shared pages berulang. Memory runner mencakup snapshot data yang dimuat kedua konfigurasi.

## 734 record — 2026-10-23T08:01:12.884241+00:00

| Metrik median | Baseline | Protected |
|---|---:|---:|
| p50 (ms) | 0.5590 | 0.8136 |
| p95 (ms) | 1.1694 | 1.8460 |
| Throughput sukses (ops/s) | 1355.3172 | 906.6213 |
| Unexpected error rate | 0.0000 | 0.0000 |
| CPU runner (% satu core) | 91.7663 | 82.8075 |
| Peak working set runner (MiB) | 81.9844 | 81.9805 |
| CPU cluster (% satu core) | 18.4083 | 9.2008 |
| Peak sum working set cluster (MiB) | 65.3906 | 54.8711 |
| Database keseluruhan (MiB) | 9.2296 | 13.0187 |
| Encrypted backup (s) | 0.1915 | 0.2283 |
| Restore baru (s) | 0.5511 | 0.6320 |
| Backup terenkripsi (MiB) | 0.1197 | 0.9677 |

p50 overhead teramati 45.5%. Lihat [raw results](../evidence/benchmark.json) untuk durasi enkripsi/dekripsi, distribusi dan variasi antar-run. Backup/restore: pg_dump custom, AES-GCM independen, restore database baru dan validasi count; tiga pengulangan per konfigurasi.

## 10,000 record — 2026-10-23T07:53:34.697680+00:00

| Metrik median | Baseline | Protected |
|---|---:|---:|
| p50 (ms) | 0.8987 | 1.0960 |
| p95 (ms) | 7.8807 | 7.3434 |
| Throughput sukses (ops/s) | 554.7684 | 475.2922 |
| Unexpected error rate | 0.0000 | 0.0000 |
| CPU runner (% satu core) | 39.6817 | 59.4115 |
| Peak working set runner (MiB) | 291.9961 | 291.9062 |
| CPU cluster (% satu core) | 11.5577 | 19.8573 |
| Peak sum working set cluster (MiB) | 41.7422 | 68.8945 |
| Database keseluruhan (MiB) | 21.1359 | 37.8312 |
| Encrypted backup (s) | 0.3483 | 1.1989 |
| Restore baru (s) | 0.9185 | 2.0798 |
| Backup terenkripsi (MiB) | 0.8244 | 15.2837 |

p50 overhead teramati 22.0%. Lihat [raw results](../evidence/benchmark-scaled.json) untuk durasi enkripsi/dekripsi, distribusi dan variasi antar-run. Backup/restore: pg_dump custom, AES-GCM independen, restore database baru dan validasi count; tiga pengulangan per konfigurasi.

## Batas interpretasi

Benchmark ini melewati HTTP, session, CSRF, audit bisnis, TLS dan live OpenBao: **NOT TESTED** untuk metrik performanya. Browser/API functional tests terpisah tidak mengubah batas ini. Storage adalah ukuran seluruh database termasuk schema, audit, users/index dan bloat; bukan ukuran ciphertext saja. Restore tidak memasukkan transfer offsite/KMS recovery. File backup benchmark berada di memori terenkripsi dan tidak dipersist; restore latency termasuk decrypt + create DB + pg_restore. Satu backup protected nyata disimpan lokal oleh backup drill terpisah.

Data scale dibuat dari nol untuk beban uji, tidak menambah anggota aplikasi atau memodifikasi sumber. Perbandingan 734 record mempunyai database yang sudah dipakai tes; 10.000 record memakai DB baru. Durasi sub-milidetik dan tiga pengulangan sensitif terhadap scheduler/cache Windows. p95 yang terkadang lebih rendah pada protected bukan bukti enkripsi mempercepat sistem.
