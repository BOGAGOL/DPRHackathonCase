# Kontrol akses aplikasi

Keputusan otorisasi dilakukan di backend pada setiap permintaan. Field yang tidak
berhak diterima tidak dimasukkan ke JSON. Frontend menampilkan DTO yang sudah dibatasi.

| Peran | Record | PII | FIN | Fungsi lain |
|---|---|---|---|---|
| operator | Assignment eksplisit | Identifier/kontak dimasking; nama detail mengikuti policy | Tidak dikirim | Update email/handphone sesuai scope |
| privileged_officer | Assignment eksplisit | PII/REF sesuai fungsi | Tidak dikirim | Insert dan update sesuai scope |
| finance_officer | Assignment eksplisit | Identitas minimal, sebagian dimasking | Diizinkan | Read-only data anggota |
| anggota | Hanya record sendiri | PII/REF miliknya | Tidak dikirim | Update kontak sendiri |
| analyst | Tidak ada akses per record | Tidak dikirim | Tidak dikirim | Agregat count≥5; total tidak tersedia |
| auditor | Tidak ada akses anggota | Tidak dikirim | Tidak dikirim | Metadata audit |

FIN: rekening, nama_rekening, npwp, kode_bank. Nama bank/KPPN merupakan REF.
Daftar hanya mengembalikan ID layanan dan nama, maksimal 50 record per halaman.
ID layanan adalah legacy_row_id; UUID kripto tetap internal. Lookup memakai blind
index. Record di luar scope ditolak tanpa mengungkap keberadaannya.

`app_user`, `analyst_user`, `auditor_user` adalah koneksi DB berbeda. Principal RLS
adalah UUID akun dan di-set LOCAL per transaksi. Anggota dicocokkan melalui binding
pengguna_bidx; staf tetap memerlukan assignment read/update/insert eksplisit.

Analytics membaca public.analyst_summary: lima marginal independen jenis_kelamin,
pekerjaan_terakhir, nama_kppn, nama_bank, age_band. Kelompok 1–4 tidak dikirim termasuk
label; total=null. Filter cohort gabungan yang belum mempunyai suppression tersendiri
ditolak HTTP422. Tidak ada fallback ke role app_user/admin untuk melayani analis.

`svc-app` dapat unwrap PII dan FIN; OpenBao tidak memahami peran HTTP. Pembatasan FIN
pada pengguna tetap kewajiban backend. Kredensial demo deployment ada di accounts.md;
credential DB dan token OpenBao tidak diberikan kepada evaluator web.
