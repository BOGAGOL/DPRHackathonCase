# Matriks akses Modul B

Kebijakan demo sintetis ini mengikuti PROMPT_B dan diterapkan di satu modul policy backend. MODE=plain dan MODE=protected memakai endpoint, pagination, dan DTO yang sama. Perbedaan mode hanya pada repository dan adapter perlindungan data; tidak ada mode yang melewati otorisasi.

| Peran aplikasi | Daftar | Detail anggota | Kontak/KTP | FIN | Agama | Perubahan kontak | Insert |
|---|---|---|---|---|---|---|---|
| `operator` | Nama dimasking | Nama penuh, kontak dan KTP dimasking | Masking server | Tidak dikirim | Tidak dikirim | `email`, `handphone` | Tidak |
| `privileged_officer` | Nama penuh | PII dan REF, kecuali FIN | Penuh | Tidak dikirim | Penuh | `email`, `handphone` | Ya |
| `finance_officer` | Nama dimasking | Identitas minimal dan informasi FIN | Nama/KTP dimasking | Penuh | Tidak dikirim | Tidak | Tidak |
| `analyst` | Ditolak | Ditolak | Tidak ada akses record | Tidak | Tidak | Tidak | Tidak |
| `auditor` | Ditolak | Ditolak | Tidak ada akses record | Tidak | Tidak | Tidak | Tidak |
| `anggota` | Hanya dirinya | Hanya PII/REF miliknya | Penuh pada record sendiri | Tidak dikirim | Penuh pada record sendiri | Hanya record sendiri | Tidak |

FIN adalah `rekening`, `nama_rekening`, `npwp`, `kode_bank`. `nama_bank` dan `nama_kppn` adalah REF sesuai kontrak; nama bank bukan alasan memberikan seluruh FIN kepada peran lain. Pengungkapan nama penuh pada detail operator mengikuti kolom Detail PROMPT_B; nama pada daftar operator tetap dimasking.

Staff internal (`operator`, `privileged_officer`, `finance_officer`) memiliki cakupan record layanan demo. Peran `anggota` selalu dibatasi di SQL sebelum pengambilan data: MODE=plain mencocokkan `pengguna` akun, MODE=protected mencocokkan `pengguna_bidx` yang dihitung oleh toolkit A. Mengganti ID pada URL, pencarian atau PATCH tidak boleh memperluas cakupan tersebut. ID yang tidak ada atau di luar cakupan tidak mengungkapkan isi record.

| Endpoint | operator | privileged_officer | finance_officer | analyst | auditor | anggota |
|---|---|---|---|---|---|---|
| `GET /anggota` | Ya, masked | Ya | Ya, masked | 403 | 403 | Hanya diri sendiri |
| `GET /anggota/{anggota_id}` | DTO operator | DTO officer | DTO finance | 403 | 403 | DTO pemilik, ID lain 404 |
| `GET /anggota/search` | DTO daftar masked | DTO daftar officer | DTO daftar masked | 403 | 403 | Hanya diri sendiri |
| `PATCH /anggota/{anggota_id}/kontak` | Ya | Ya | 403 | 403 | 403 | Hanya diri sendiri |
| `POST /anggota` | 403 | Ya | 403 | 403 | 403 | 403 |
| `GET /analytics/summary` | 403 | 403 | 403 | Agregat saja | 403 | 403 |
| `GET /audit` | 403 | 403 | 403 | 403 | Metadata audit | 403 |

Semua endpoint di atas membutuhkan session sah. Login/logout/CSRF merupakan fungsi sesi semua peran. Tidak ada peran admin universal yang otomatis membaca seluruh PII/FIN.

Koneksi data anggota memakai DB role `app_user`. Analytics membuka koneksi berbeda sebagai `analyst_user`, hanya pada `analyst_view`; audit dibaca dengan `auditor_user`, hanya pada `audit_log`. Identitas aplikasi bukan role PostgreSQL. `app.principal` diset lokal pada transaksi untuk integrasi RLS; RLS tidak menggantikan predicate pemilik pada backend.

Daftar hanya mengembalikan `anggota_id` dan `nama`, dengan pagination 50 record. Detail memakai allowlist per peran pada backend; kolom yang dilarang tidak dikirim sebagai null/placeholder maupun tersembunyi dalam JSON. Kontak baru divalidasi, hanya dua field yang dapat diubah, dan email blind index diperbarui dalam transaksi yang sama pada MODE=protected. Keputusan deny merupakan default jika peran, record, field, atau dependensi crypto tidak cocok.

Policy svc-app OpenBao yang sama dapat unwrap PII dan FIN; pembatasan FIN adalah kewajiban policy aplikasi. Jangan mengklaim policy Transit mengetahui peran pengguna atau endpoint HTTP.
