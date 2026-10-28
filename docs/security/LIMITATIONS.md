# Keterbatasan solusi dan bukti

Dokumen ini wajib dibawa ke laporan dan slide. Kata "terlindungi" selalu menyebut
kolom, artefak, penyerang, kemampuan kunci, dan lingkungan yang sedang dibahas.

| Area | Batas yang harus disampaikan |
|---|---|
| Kompromi bersama | Aplikasi dengan data dan kemampuan decrypt yang dikuasai tidak lagi menjamin kerahasiaan |
| Pemisahan domain | PII/FIN membatasi kemampuan tertentu; token svc-app runtime dapat unwrap kedua domain, otorisasi field tetap tugas backend |
| Blind index | Mengungkap equality/frequency dan dapat mendukung dictionary attack jika search capability ikut bocor |
| REF/NULL | Jenis kelamin, pekerjaan, institusi/bank, age_band dan pola NULL tetap terlihat pada tabel/dump bagi pihak yang mendapat artefaknya |
| A5 | Suppression berlaku pada lima marginal yang dirilis; bukan differential privacy atau jaminan k-anonymity kombinasi/antarwaktu |
| RLS | `app.principal` bisa diubah oleh pencuri credential app_user; pertahanan utama tetap autentikasi/otorisasi backend |
| Data at rest | Enkripsi field tidak mengenkripsi seluruh filesystem, metadata, source/baseline atau log; bukti dump logis tidak membuktikan file data/WAL |
| Lingkungan lab | Source 734 dan baseline plaintext berada di instance lab; jangan mengklaim salinan seluruh pg-dpr hanya berisi ciphertext |
| Memori/cache | DEK dipakai lokal, cache dibatasi TTL/ukuran; Python/OS tidak menjamin zeroization seluruh salinan atau swap/crash dump |
| Backup/retensi | Record hilang dari backup baru setelah dihapus; backup lama dapat memuatnya sampai retensi berakhir. Deadline bukan scheduler purge/secure erase SSD |
| Recovery kunci | Salinan encrypted DB tanpa key-plane/kunci backup tidak cukup; DPAPI laptop bukan escrow lintas mesin. DR seluruh server/key-plane belum dibuktikan |
| Artefak backup tepercaya | HMAC/integritas mengasumsikan produsen dan kunci signing tidak dikuasai penyerang; restore SQL mempunyai kemampuan DDL privileged |
| Audit | Audit minim nilai pribadi, tetapi tidak diklaim immutable atau tahan administrator OS/DB yang berkuasa |
| Scanner | Evaluasi 29 kolom in-sample pada satu tabel; angka tinggi bukan akurasi universal. Nama disamarkan diuji, ground truth masih perlu pengesahan manusia |
| Dataset | Data sintetis panitia; tidak memvalidasi data produksi instansi atau dasar hukum pemrosesan nyata |
| Bukti A5/restore | 143 pemeriksaan nyata memakai 17 record buatan sendiri; tidak menggantikan pengujian seluruh dataset 734/100k/1m |
| Deployment web | 100 pemeriksaan melalui enam akun, tanpa SSH; commit, ACL SQL dan TLS backend internal VM tidak diperiksa langsung dalam bukti ini |
| Kinerja | Snapshot ini mempunyai baseline awal; belum mempunyai before/after protected/API resmi lengkap. Hasil branch lain belum menjadi hasil branch ini |
| TLS benchmark | Non-TLS hanya pengecualian dua role pada baseline/IP terkontrol; bukan konfigurasi produksi dan tidak berlaku pada protected |
| Operasional | Token svc-app berbatas TTL, manual unseal, rotasi/revokasi dan pembaruan sertifikat perlu operator; ketersediaan tanpa operator tidak dijamin |
| Supply chain | Python SBOM direct-only; tag postgres:18 belum berupa patch/digest tetap; inventaris bukan audit CVE menyeluruh |
| Pengumpulan | Draf Markdown dan source ZIP bukan PDF laporan/slide final; akses Drive dan kesamaan berkas presentasi perlu diperiksa tim |

Jangan mengganti status yang belum diuji menjadi PASS agar checklist terlihat penuh.
Prioritas tindak lanjut ada pada [checklist](../submission/CHECKLIST.md), sedangkan
scope per klaim ada pada [indeks evidence](../evidence_index.md).
