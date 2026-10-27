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
