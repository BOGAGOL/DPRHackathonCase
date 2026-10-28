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
