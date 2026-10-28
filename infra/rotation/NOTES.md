# Keputusan dan batas tahap 6

- Kontrak tidak berubah. `pii-kek` berotasi lalu wrapped DEK direwrap lewat Transit;
  field AES-GCM lokal beserta nonce/AAD tetap sama. Versi `vault:v2:` adalah versi
  **KEK**, bukan `protection_version` atau format ciphertext field.
- Referensi API dibaca pada [OpenBao Transit](https://openbao.org/docs/api/secret/transit/).
  Perilaku rotate, respons kosong HTTP 204, batch_input dengan reference dan
  key_version per item diuji langsung pada OpenBao **2.5.5**. Rewrap tidak mengembalikan
  plaintext DEK; client gagal tertutup pada partial batch/reorder/versi salah.
- Memakai tiga proses: coordinator `admin_user`, worker OpenBao `key-operator`
  tanpa kredensial PG/decrypt, dan validator `scanner_user` + `svc-app`. Environment
  subprocess dibangun dari allowlist, bukan salinan os.environ. Root token, lokasi
  DPAPI dan kredensial bootstrap tidak diteruskan. IPC hanya private pipes; stderr
  child tidak dicetak/disimpan. Operator worker tidak pernah menerima field data.
- Pemisahan environment/process di laptop operator bukan sandbox OS atau bukti
  pemisahan manusia. Coordinator/operator laptop tepercaya dapat menyediakan
  beberapa credential. Produksi membutuhkan custodian/host terpisah dan kebijakan
  akses OS; token key-operator sendiri tidak diberi role database.
- SQL tambahan **tidak menambah tabel/role** sehingga backup tahap 5 tetap cocok.
  Tiga fungsi SECURITY DEFINER dengan search_path pg_catalog dimiliki schema_owner
  NOLOGIN dan EXECUTE hanya admin_user. Status/page hanya mengembalikan metadata
  wrapped PII, apply hanya menerima UUID + wrapped lama/baru. Tidak memberi admin
  SELECT/UPDATE tabel anggota atau akses FIN/field plaintext. Policy update untuk
  schema_owner diperlukan karena FORCE RLS; owner sudah dipercaya untuk DDL.
- Apply memeriksa bound <=100, shape/ukuran ciphertext, target versi, CAS, tanpa
  downgrade. Batch atomik; idempotensi dari versi wrapped yang tersimpan. Tidak ada
  checkpoint DEK di disk. Audit per-row dan updated_at normal tetap dijalankan.
  Jika provisioning tahap 3 diulang, grant fungsi dapat dicabut oleh reset ACL;
  jalankan `infra.rotation prepare` lagi sebelum rotasi, jangan aktifkan ulang
  migration_user yang sudah NOLOGIN untuk keperluan rotasi.
- Validator membaca **semua record dan semua field PII/FIN**, bukan sampel. Unwrap
  100 record per batch; plaintext/DEK hanya di memori. Tiga pembanding before/after:
  SHA256 atas seluruh row ciphertext/metadata kecuali wrapped PII dan updated_at;
  HMAC atas nilai field dengan kunci CSPRNG sementara; HMAC atas UUID + DEK_PII +
  DEK_FIN. HMAC key/digest tidak keluar validator/tidak dipersist. Evidence hanya
  count dan boolean. Ini membuktikan DEK, ciphertext, FIN, bidx, REF dan nilai data
  tetap sama sekaligus autentikasi field masih berhasil. Memori dibatasi 100 record.
- Tidak mengubah min_decryption_version, min_encryption_version, menghapus versi
  lama, atau merotasi finance-kek/search-hmac. Backup lama harus tetap bisa dibaca.
  Menghapus versi key lama adalah operasi lain yang perlu inventaris seluruh
  backup/replica/DB, bukan bagian tahap 6.
- Tidak ada retry rotate otomatis. HTTP timeout setelah commit rotasi di OpenBao
  bersifat ambigu; metadata/custodian menentukan versi resume. Rewrap memakai
  versi tujuan eksplisit, CAS dan checkpoint setelah batch commit. Partial progress
  tetap aman karena OpenBao mempertahankan versi lama; resume wajib versi yang sama.
- Penulisan checkpoint atomik memakai bounded retry untuk PermissionError Windows
  ketika antivirus/pembaca sedang membuka file laporan. Retry hanya mengganti
  file JSON, tidak mengulang rotasi OpenBao atau transaksi DB yang sudah commit.
  Temporary report dibersihkan pada kegagalan; perilaku transient/permanent file
  lock diuji dengan fault injection.
- Jendela maintenance diperlukan untuk bukti before/after yang stabil. Advisory
  lock melindungi coordinator yang memakai protocol ini pada DB yang sama, bukan
  seluruh key plane lintas cluster. Penulisan aplikasi/rotasi operator lain dapat
  membuat verifikasi gagal. Tool tidak menurunkan/menonaktifkan key version sebagai
  upaya rollback; lakukan resume setelah konflik diselesaikan.

## Hasil lokal 28 Oktober 2026 (WIB)

Tahap 5 sudah di-merge melalui PR #4 (`5ab5248`). Fungsi rotation kemudian
diterapkan eksplisit ke protected_734/protected_100k; tidak membuat ulang container,
tidak menjalankan ulang migrasi dan migration_user tetap NOLOGIN.

`pii-kek` berotasi **v1 → v2** satu kali. Seluruh **734 + 100.000 wrapped DEK PII**
kini v2. Domain finance-kek/search-hmac tetap v1; min_decryption_version tetap 1.
Seluruh field PII/FIN didekripsi dan dibandingkan before/after; DEK, ciphertext,
wrapped FIN, blind index dan REF tetap sama. NULL dipertahankan.

Eksekusi awal terhenti setelah 734 + 54.600 baris commit dan meninggalkan temporary
checkpoint. Penulisan checkpoint Windows diberi bounded retry dan fault-injection
test, lalu resume **versi 2 yang sama** menyelesaikan 45.400 sisanya. Tidak ada
rotasi kedua. `rotation-first-attempt.json` adalah bukti historis kegagalan yang
superseded, bukan hasil akhir; `rotation.json` adalah hasil akhir passed.
Report akhir menyertakan versi awal keseluruhan, distribusi versi dan total baris
lintas kedua attempt. Total waktu kedua attempt 228.269197 detik mencakup validasi
ulang, bukan benchmark rotasi tanpa interupsi.

Sebagai pemeriksaan tambahan setelah resume, setiap record dan seluruh kolom
(termasuk blind index/NULL) dibandingkan kembali terhadap sumber postgres dan
baseline_100k: **100.734/100.734 cocok** tanpa mencetak plaintext. Checksum kedua
sumber resmi sebelum/sesudah tetap sama. Backup protected_734 yang dibuat sebelum
rotasi berhasil restore dan smoke decrypt kedua domain; scratch DB dibersihkan.
Token operator/validator sementara dicabut, termasuk token perbandingan tambahan.

Bukti: `evidence/keys/rotation.json`, `post-rotation-validation.json`,
`source-preservation.json`, `backup-compatibility.json`,
`validation-token-revocation.json`, `integration.json` dan `test-results.json`.
Data protected_1m belum tersedia lokal; CLI mendukungnya, eksekusi di laptop rekan
benchmark memerlukan key plane dan token milik laptop tersebut.
