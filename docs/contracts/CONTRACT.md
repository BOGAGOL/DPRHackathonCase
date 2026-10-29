# Spesifikasi data terproteksi v1

Format field, associated data, blind index dan kewenangan digunakan bersama oleh
migrator, aplikasi dan verifier. Perubahan format memerlukan protection_version baru.
Identitas input format lama pada profile dijaga melalui policy/protocol-v1.txt;
pembersihan dokumentasi tidak mengubah ciphertext atau memerlukan migrasi ulang.

## 1. Database dan lingkungan

| Nama | Isi | Pemilik |
|---|---|---|
| `postgres` (db) | 734 baris asli, plaintext, TIDAK BOLEH DIUBAH | - |
| `baseline_100k` | Data sintetis 100k plaintext (sistem "before") | Verifikasi (C) |
| `protected_100k` | Hasil migrasi dari `baseline_100k` (sistem "after"), database BARU | Data & Crypto (A) |
| `protected_734` | Hasil migrasi dari 734 baris asli, untuk demo | Data & Crypto (A) |

OpenBao: container terpisah, Transit engine di mount `transit/`.

## 2. Kunci di OpenBao (key plane)

| Nama kunci Transit | Tipe | Fungsi |
|---|---|---|
| `pii-kek` | aes256-gcm96 | Membungkus DEK_PII per record |
| `finance-kek` | aes256-gcm96 | Membungkus DEK_FIN per record |
| `search-hmac` | hmac (atau aes256 untuk endpoint /hmac) | Membuat blind index; key per kolom diturunkan via label domain |

DEK dibuat per record lewat `transit/datakey/wrapped/<kek>` atau dibuat lokal (CSPRNG 32 byte)
lalu dibungkus lewat `transit/encrypt/<kek>`. Database hanya menyimpan wrapped DEK.

Policy OpenBao (nama policy -> hak):
- `svc-app`: decrypt/unwrap `pii-kek`, decrypt/unwrap `finance-kek` (hanya dipakai endpoint finance), hmac `search-hmac`, encrypt untuk insert/update.
- `svc-migration`: encrypt/datakey `pii-kek`, `finance-kek`, hmac `search-hmac`. Dicabut setelah migrasi.
- `svc-verify`: TIDAK punya decrypt (dipakai untuk simulasi bocor tanpa kunci).
- `key-operator`: rotate/rewrap/config, tidak punya akses ke database.
Tidak ada service yang memakai root token.

## 3. Domain dan perlakuan kolom (protection profile)

File mesin: `policy/protection_profile.yaml` (dibangun dari hasil scanner dan override kebijakan).

| Kolom | Domain | Simpan sebagai | Blind index | Proyeksi analis |
|---|---|---|---|---|
| nama, nama_lengkap, nama_tanpa_gelar | PII | AEAD | - | tidak |
| jenis_kelamin | - | plaintext (REF) | - | ya |
| tempat_lahir | PII | AEAD | - | tidak |
| tanggal_lahir | PII | AEAD | - | `age_band` (plaintext turunan, mis. "40-49") |
| tanggal_pernikahan | PII | AEAD | - | tidak |
| no_ktp | PII | AEAD | `no_ktp_bidx` | tidak |
| pekerjaan_terakhir | - | plaintext (REF) | - | ya |
| alamat_jakarta, alamat_daerah | PII | AEAD | - | tidak |
| telpon_jakarta, telpon_daerah, handphone | PII | AEAD | - | tidak |
| email | PII | AEAD | `email_bidx` | tidak |
| ruangan | PII | AEAD | - | tidak |
| status_kawin | PII | AEAD | - | tidak (aggregate via fungsi khusus jika perlu) |
| jumlah_anak, jumlah_tanggungan, jumlah_jiwa | PII | AEAD | - | tidak |
| rekening, nama_rekening, npwp, kode_bank | FIN | AEAD | - | tidak |
| nama_kppn, nama_bank | - | plaintext (REF) | - | ya |
| nip_kppn | PII | AEAD | - | tidak |
| pengguna | PII | AEAD | `pengguna_bidx` | tidak |
| agama | PII | AEAD | - | tidak |

Catatan keputusan:
- `kode_bank` dimasukkan domain FIN (bukan REF seperti di PDF) karena di dump ini nilainya acak
  dan hampir unik per orang (373 baris unik sendirian; bersama kolom plaintext lain unik 100%).
- Kolom plaintext yang tersisa setelah hardening (jenis_kelamin, pekerjaan_terakhir, nama_kppn,
  nama_bank, age_band) WAJIB diuji k-anonymity oleh verifier.
- Tidak ada kolom yang dihapus. Kandidat minimisasi (3 kolom nama identik) hanya didokumentasikan.
- Password akun aplikasi (tabel users aplikasi) memakai Argon2id, bukan enkripsi.

## 4. Skema tabel terproteksi `anggota_protected`

```sql
CREATE TABLE anggota_protected (
  anggota_id          uuid PRIMARY KEY,          -- UUIDv4 acak, bukan id berurutan
  legacy_row_id       bigint UNIQUE NOT NULL,    -- id dari baseline, untuk validasi migrasi
  protection_version  smallint NOT NULL,         -- mulai 1
  dek_pii_wrapped     text NOT NULL,             -- ciphertext OpenBao "vault:vN:..."
  dek_fin_wrapped     text NOT NULL,
  -- satu kolom bytea per field AEAD, nama: <kolom>_ct
  nama_ct bytea, nama_lengkap_ct bytea, ... , agama_ct bytea,
  -- blind index
  no_ktp_bidx bytea, email_bidx bytea, pengguna_bidx bytea,
  -- plaintext REF dan turunan
  jenis_kelamin char(1), pekerjaan_terakhir varchar(50), nama_kppn varchar(50), nama_bank varchar(50),
  age_band varchar(10),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON anggota_protected (no_ktp_bidx);
CREATE INDEX ON anggota_protected (email_bidx);
CREATE INDEX ON anggota_protected (pengguna_bidx);
```
Nilai NULL di sumber disimpan sebagai NULL (bukan ciphertext dari string kosong). Fakta "kolom
ini NULL" adalah kebocoran yang diterima dan dicatat (contoh: tanggal_pernikahan).

## 5. Format ciphertext field (v1)

```
blob = version(1 byte = 0x01) || nonce(12 byte, acak per enkripsi) || ciphertext||tag(16 byte)
```
- Algoritma: AES-256-GCM, kunci = DEK_PII atau DEK_FIN record tersebut.
- Plaintext: string UTF-8. Tanggal ISO `YYYY-MM-DD`. Angka sebagai string desimal.
- Nonce TIDAK BOLEH dipakai ulang; selalu dari CSPRNG.

## 6. Format AAD (v1)

```
AAD = "dpr|v1|anggota_protected|" + <nama_kolom> + "|" + <anggota_id lowercase> + "|" + <protection_version>
```
Contoh: `dpr|v1|anggota_protected|rekening|3f6c...e1|1` (UTF-8 bytes).
Akibatnya ciphertext yang dipindah ke kolom lain atau record lain GAGAL didekripsi.

## 7. Blind index (v1)

```
normalized = normalize_<kolom>(value)
bidx = HMAC-SHA256(key = search key, msg = "bidx|v1|" + <nama_kolom> + "|" + normalized)  -> 32 byte
```
- Jika memakai OpenBao `transit/hmac/search-hmac`, input dan label sama, hasil disimpan sebagai bytes.
- Normalisasi: `no_ktp` = hanya digit, tanpa trim nol; `email` = trim + lowercase seluruhnya;
  `pengguna` = trim (case-sensitive). Normalisasi tercatat di profile, jangan diubah tanpa versi baru.

## 8. Aturan wajib
- Gagal dekripsi = error (fail closed). Dilarang fallback ke plaintext atau nilai default.
- Dilarang mencetak plaintext, DEK, token, atau password ke log.
- Semua query berparameter.
- Kredensial hanya dari environment variable; `.env` tidak di-commit.

## 9. Test vector bersama
`docs/contracts/test_vectors.json` berisi vector uji publik: DEK contoh (khusus test), anggota_id, kolom,
plaintext, AAD, nonce, blob hasil, dan bidx hasil dengan search key contoh. Aplikasi WAJIB lulus
test yang mendekripsi vector ini (terutama jika backend bukan Python).

## 10. Role database
| Role | Hak |
|---|---|
| `schema_owner` | NOLOGIN, pemilik objek |
| `app_user` | SELECT/INSERT/UPDATE pada anggota_protected + tabel aplikasi; NOSUPERUSER, NOBYPASSRLS, tanpa DDL |
| `analyst_user` | SELECT hanya `analyst_summary` (agregat k>=5) dan EXECUTE `analyst_age_summary()` yang membaca agregat itu; tanpa akses per record |
| `auditor_user` | SELECT tabel `audit_log`; tidak ke data anggota |
| `backup_user` | Hak minimum untuk pg_dump; tidak punya kredensial OpenBao |
| `admin_user` | Administrasi terbatas, tercatat; tidak punya kredensial OpenBao decrypt |
| `migration_user` | Sementara, dicabut setelah migrasi |
| `scanner_user` | Read-only untuk scanner |

### 10.1. Interface analis A5: agregat dengan ambang 5

`public.analyst_view` tetap merupakan proyeksi internal REF + age_band per record dan
**tidak boleh dibaca `analyst_user`**, termasuk melalui grant per kolom. Tabel dasar,
tabel akun/sesi, dan proyeksi per record lainnya juga tidak boleh dibaca role ini.

Interface baru: `public.analyst_summary`, view milik NOLOGIN `schema_owner`, dengan
`security_barrier=true` dan owner rights (`security_invoker=false`):

| Kolom | Tipe | Arti |
|---|---|---|
| `dimension` | text | Salah satu `jenis_kelamin`, `pekerjaan_terakhir`, `nama_kppn`, `nama_bank`, `age_band` |
| `value` | text, nullable | Label kelompok; NULL berarti kelompok nilai NULL |
| `anggota_count` | bigint | Jumlah anggota, selalu >= 5 |

View berisi lima marginal satu dimensi yang dihitung secara independen menggunakan
`GROUP BY <dimensi> HAVING count(*) >= 5`, digabung `UNION ALL`. Kelompok berukuran
1–4 **tidak menghasilkan baris sama sekali**, termasuk labelnya. NULL dihitung dengan
`count(*)`, sehingga kelompok NULL juga tunduk pada ambang. Tidak ada UUID, legacy id,
ciphertext, wrapped DEK, atau kombinasi atribut per anggota di interface ini.
`analyst_age_summary()` mempertahankan kolom `(age_band varchar(10), anggota_count bigint)`
dan kini membaca hanya marginal `age_band` pada view baru, dengan SECURITY INVOKER.

Endpoint analytics membaca view agregat dengan query berparameter berikut;
`anggota_count` dipetakan menjadi `groups[].count` pada DTO:

```sql
SELECT dimension, value, anggota_count
FROM public.analyst_summary
ORDER BY dimension, value NULLS LAST;
```

Jangan melakukan `count(*)` atas view baru untuk menghitung jumlah anggota; hasilnya
adalah jumlah kelompok. Jangan menjumlahkan lintas dimensi (anggota terhitung berulang).
`total` pada DTO harus `null`: view ini tidak menyediakan total mentah/kelompok tersembunyi.
Jangan mengirim label kelompok kecil dengan `"<5"` sebagai count. Filter SQL di atas
view hanya boleh memilih marginal yang sudah dirilis (`dimension`/`value`), bukan
menyimulasikan cohort gabungan. Filter anggota seperti `nama_kppn` + `pekerjaan_terakhir`
pada endpoint lama harus ditolak secara eksplisit (misalnya HTTP 422) sampai tersedia
interface SQL agregat terfilter dengan suppression tersendiri; jangan fallback ke query
per record, role app_user, atau query admin. Otorisasi endpoint tetap dilakukan backend.

Penerapan harus dikoordinasikan dengan rilis aplikasi (maintenance endpoint analytics
sampai query baru aktif). CLI khusus A5 tidak mengubah LOGIN role migrasi, password,
grant tabel Service App, atau isi anggota. Backup lama yang terautentikasi juga mendapat
upgrade ACL A5 pada restore sebelum CONNECT runtime dibuka. Panduan operasi: `docs/OPERATIONS.md`.

**Batas klaim:** ambang ini berlaku untuk setiap marginal yang dirilis. Ini bukan
k-anonymity atas seluruh kombinasi REF, differential privacy, atau perlindungan mutlak
dari inferensi melalui pengetahuan tambahan, perbedaan antarwaktu, dan penggabungan hasil.
Kolom REF tetap tersimpan pada tabel dasar untuk role yang memang diizinkan/dump.
