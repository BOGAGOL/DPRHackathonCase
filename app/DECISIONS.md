# Keputusan Modul B

## 28 Oktober 2026 — kontrak analis A5/B4

- CONTRACT 10.1 terbaru mengikat. B tidak mengubah toolkit, SQL A, protection_version
  atau sumber dataset. A5 adalah perubahan ACL/agregat, tanpa enkripsi ulang.
- Query public.analyst_summary hanya tiga kolom, filter terikat dimension/value dan
  anggota_count >=5 sebagai pertahanan tambahan. Tidak ada COUNT total/penjumlahan
  lintas dimensi atau query anggota fallback.
- DTO mempertahankan kunci total/groups, tetapi total hanya null dan count hanya
  integer >=5. Tidak ada label kelompok kecil maupun placeholder <5. Ini mengganti
  perilaku suppression lama yang masih menampilkan labelnya.
- Value memerlukan dimension; filter atribut anggota lama ditolak 422 eksplisit.
  UI memilih marginal yang sudah dirilis, tidak menawarkan cohort gabungan.
- SQLite fixture menerjemahkan schema public hanya saat settings.testing. Runtime
  PostgreSQL tetap menanyakan public.analyst_summary dengan analyst_user.
- View plain untuk lab B/disposable mengikuti marginal ambang 5 yang sama. Perubahan
  setup hanya source; tidak diterapkan selama benchmark atau ke pg-dpr existing.
- Rilis VM memakai maintenance aplikasi, update source/build, CLI SQL A5 kanonis,
  verify, kemudian runtime. Tidak prepare/provision ulang. Bukti lokal dan VM dicatat
  terpisah; evidence lama tanpa cek A5 tidak boleh mengesahkan rilis baru.


## 28 Oktober 2026 — perbaikan visual filter analytics

Gunakan Button shared agar style konsisten dan hindari class CSS yang tidak ada.
Field mempunyai label terpisah dan ruang isi kartu; desktop dua kolom, mobile satu
kolom. Satu aksi utama Terapkan dan aksi sekunder Reset; tidak menggunakan link
untuk tindakan form. Hapus kartu total tanpa nilai dan teks berulang; total API tetap
null sesuai A5. Rilis ini hanya frontend dan tidak memerlukan SQL/migrasi ulang.


## 28 Oktober 2026 — hapus dekorasi dan penjelasan teknis

Ikuti screenshot pengguna: hapus panel promosi login, kartu keamanan sidebar,
indikator sesi dan catatan backend pada profil. Tampilkan form login tunggal dan
identitas akun/logout yang diperlukan. Hapus markup/CSS yang tidak dipakai; hindari
sekadar display:none. Pembatasan akses tetap menjadi perilaku sistem, bukan paragraf
penjelasan pada setiap layar. Source hanya app/, tanpa perubahan backend/database.

## 28 Oktober 2026 — pentest accounts dan template recovery VM

Ikuti prompt revisi: demo tetap,8 pt terpisah dengan scope minimal5+5/owner unik,
tanpa endpoint provisioning publik. Gunakan schema akun/binding/scope existing A/B
dan Argon2id resmi, tidak menyentuh row anggota saat persiapan. Golden memakai
PostgreSQL18 CREATE DATABASE TEMPLATE sesuai permintaan, bukan implementasi crypto
atau backup baru. Identitas cluster/live/golden/OID diperiksa sebelum DROP target
fixed protected_734; ALLOW_CONNECTIONSfalse mencegah koneksi baru saat reset.

Karena VM masih memakai foreground, sediakan hanya dua unit DPR yang dapat
dikendalikan skrip, tidak pkill, reboot, stop Docker/Nginx atau menyentuh service Ardi.
Browser web tidak menerima token/DB URL melalui environment Node, tetapi user OS
masih ubuntu bersama; tidak mengklaim isolasi RCE penuh. Dua source path tambahan
docs/deploy/ dan scripts/deploy/ berasal dari permintaan eksplisit terbaru pengguna.
Golden mengembalikan pt aktif; disable terakhir sesudah restore. Bukti unit dan
VM dipisahkan: operator kemudian menjalankan satu reset nyata PASSED dan metadata
diunduh; vm-golden-reset.json menjadi bukti, bukan test fake catalogue.

## 29 Oktober 2026 — exact opt-in target clone benchmark

Tambahkan DPR_BENCHMARK_DATABASE, bukan menerima sembarang DATABASE_URL atau
mengganti nama database original untuk memenuhi allowlist. Namespace api_ hanya
aktif jika dipilih operator; seluruh koneksi harus target sama dan tidak bisa
digabung dengan recovery override. Format crypto/DTO/otorisasi/target performa tetap.

Setup resmi B memberi hak koneksi/schema pada clone saja; runtime tetap app_user
verify-full, tanpa DDL, dengan gate metadata read-only dan FORCE RLS protected.
Marker mode menyatakan setup disetujui, bukan pengganti verifikasi clone milik C.
Load generator CA file, lifecycle token dan cleanup tetap tanggung jawab A/C;
tidak mengubah TLS agar benchmark lolos. Gunakan checkout terpisah karena root
pengguna sedang merge; commit patch hanya app/.

## 29 Oktober 2026 — dependency security release

Upgrade memakai worktree terpisah dan venv baru agar environment lama tetap utuh.
Rentang cryptography50.x berasal dari review Modul A; pytest dipin9.0.3 pada
requirements aplikasi/tooling. Tidak mengubah dependency referensi buku historis.
VM bukan Git checkout: commit sebelum deployment harus null/unknown, bukan ditebak.
Rilis dikaitkan ke commit main melalui manifest hash subset source yang dipasang.
Backup kode dan venv lama wajib tersedia sebelum mutasi; hanya dua service DPR
boleh di-restart. Smoke existing harus lulus sebelum dan sesudah upgrade; tidak
menggunakan provisioning, reset database atau rotasi kunci untuk menutupi kegagalan.

## F-01 — KTP unik, 29 Oktober 2026

Instruksi Zhafif menetapkan satu no_ktp non-NULL hanya satu record anggota. Tambah
sql/protected/04_identity_unique.sql, unique index bidx global/nondeferrable tanpa
plaintext, penolakan duplikat sebelum DDL dan verifikasi indeks existing agar tidak
salah menerima indeks nonunique/partial. NULL sumber tetap dapat berulang; tidak
mengubah format v1, normalisasi toolkit, ciphertext atau sumber734. Email/pengguna
belum memiliki aturan bisnis unik eksplisit sehingga tidak ikut diberi unique.

API menangkap hanya unique violation indeks KTP yang diharapkan, rollback sebelum
audit denied, balas409 generik tanpa ID/nilai/bidx. Integrity error lain tetap503.
Form POST menormalisasi digit/spasi/titik/tanda hubung sebelum validasi14/16digit;
nol awal dipertahankan. Plain API cek atomik dengan advisory transaction lock
per identitas pada PG, tanpa mengubah schema/data baseline milik C. Proteksi
persistensi terhadap semua writer ditegakkan pada protected; raw SQL baseline
bukan jalur layanan dan tidak mendapatkan constraint baru.

Tes482PASS/3SKIP, termasuk9native PG18 pada cluster disposable bertanda khusus:
request HTTP bersamaan menghasilkan201+409 dan search1, konflik tetap ditolak
meski record tersembunyi oleh RLS, migrasi fail closed/idempotent dan NULL terjaga.
Skipped: satu integrasi existing opt-in dan dua kasus RLS yang tidak berlaku plain.
Uji native memakai transport lokal disposable dan crypto test double; tidak mengaku
menguji TLS/OpenBao nyata lewat test tersebut. Evidence VM masih PENDING.

Reset golden lama sekarang memasang ulang indeks F-01 sebelum start aplikasi;
kegagalan migrasi menjaga service berhenti. Golden tidak dimodifikasi. Restore
backup lama Modul A juga harus menerapkan SQL04 sebelum membuka write API kembali.
Penerapan VM yang diminta: simpan metadata/audit, reset golden resmi, pasang SQL04
serta kode, restart hanya dpr-api/dpr-web dan smoke65. Akun pt tetap aktif sampai
retest Delf; disable paling akhir. Baseline benchmark/hasil historis tidak diubah.
