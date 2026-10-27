# Ground Truth Assessment — Hackathon DPR RI 2026

## Keluaran dan cakupan

- `ground_truth_filled.csv`: **30 baris**, struktur CSV asli dipertahankan. Baris `id` memiliki **label kondisional** tetapi tidak boleh diikutsertakan dalam penilaian terhadap SQL dump asli.
- `ground_truth_eval.csv`: **29 baris**, hanya kolom yang benar-benar ada pada seluruh INSERT; **gunakan file ini untuk menghitung precision, recall dan F1 scanner** terhadap dump sumber.
- Source SQL: `anggota_dummy.sql`, **734 INSERT** untuk `anggota`, **29 kolom eksplisit**, **tanpa perintah CREATE TABLE**. Nama `public.anggota` mengikuti template CSV pengguna, bukan schema yang ditemukan dalam SQL MySQL.

## Landasan dan peraturan penilaian

**Sumber lomba:** Soal Final Hackathon DPR RI 2026 — Tantangan 1 meminta menemukan data berdasarkan struktur, nama, isi, teks bebas, relasi, dan menguji akurasi terhadap klasifikasi acuan tim. Dokumen *Detail Hackathon* menentukan komponen data inventory: lokasi, pola tanpa nilai lengkap, tipe, kelas PDP, risiko, alasan, dan rekomendasi.

**PDP:** UU Nomor 27 Tahun 2022, Pasal 1 dan Pasal 4. Kelas `umum` mencakup nama lengkap, jenis kelamin, agama, status perkawinan, serta data yang dikombinasi untuk identifikasi; kelas `spesifik` mencakup *data keuangan pribadi* dan kategori tertentu lainnya. HANYA `rekening` diberi spesifik untuk 29 kolom yang tersedia karena itulah atribut langsung nomor akun finansial. `nama_rekening` sendiri adalah nama pribadi umum meskipun berkaitan erat dengan `rekening`.

**Pak Onno:** *Data Leak-Proof* (2026), Bab 1.3 hal. 24–25 membedakan direct identifier, quasi-identifier, data finansial, metadata, minimisasi; Bab 2.7 hal. 60–62 mengajarkan skor enam faktor untuk risiko prioritas; Bab 3.7 hal. 87–89 protection profile. *Overview Serangan ke Data dan Database*, Bab 1–3, membahas attack paths dan inferensi dari hubungan data.

## Aturan pelabelan

1. `is_personal=1` jika atribut menjelaskan orang atau menjadi identifier tertaut secara langsung ataupun gabungan (termasuk kategori umum UU PDP); bukan berarti harus dienkripsi satu per satu.
2. `is_personal=0` untuk nilai referensi **institusi** seperti `nama_kppn`, `nama_bank`, `kode_bank`. **Nuansa:** ketika tiga atribut tersebut ditautkan pada individu bersama `rekening`, hubungan dan rekonstruksi finansial tetap bisa menjadi informasi pribadi. Label kolom institusi sebagai non-pribadi adalah konvensi evaluasi deteksi pada *jenis nilai*, bukan izin membocorkan seluruh barisnya.
3. `risk_level` memakai `rendah / sedang / tinggi / kritis` sebagai **penilaian awal** berdasarkan ancaman dump plaintext yang dicuri dan potensi penyalahgunaan; **bukan hasil skor 6 faktor** karena hak akses produksi, volume nyata, insiden, dan recovery sesungguhnya belum tersedia. Skor yang ditentukan dengan enam faktor dapat dilengkapi dalam matriks risiko terpisah.
4. `pdp_class` bukan `risk_level`: agama termasuk **umum** menurut Pasal 4(3) tetapi dalam konteks profiling diberi risiko **tinggi**; nomor rekening **spesifik** sekaligus **kritis**.
5. **Kolom `id` tidak ada dalam dump**, sehingga label personalnya hanyalah dugaan ID record apabila target database nantinya membuat primary key auto-generated. Jangan memasukkan `id` dalam denominator metrik.
6. Label dianggap hasil **review awal berbasis SQL dan referensi**, bukan acuan yang sudah disahkan tim. Dua reviewer independen sebaiknya menandatangani pilihan kelas khususnya `nip_kppn` serta metadata institusi.

## Temuan yang diverifikasi dari seluruh 734 record

| Pemeriksaan | Temuan |
|---|---|
| Total record | 734 |
| Kolom data dalam SQL | 29 (`id` tidak muncul) |
| Kolom `nama`, `nama_lengkap`, `nama_tanpa_gelar` | Selalu mempunyai isi yang sama |
| `no_ktp` | Seluruhnya 14 digit, berbeda dari NIK standar 16 digit; identifier bertipe KTP-like |
| `rekening` | Seluruhnya 16 digit (data dummy); disimpan sebagai string untuk mempertahankan nol di depan |
| `npwp` | Seluruhnya 15 digit (pola NPWP lama) |
| `nip_kppn` | Seluruhnya 18 digit |
| `tanggal_pernikahan` | 367 NULL; 42 nilai non-NULL mendahului `tanggal_lahir` |
| `ruangan` | 734 kode unik `DUMMY-001` ... `DUMMY-734`; dapat menjadi proxy record ID |
| `kode_bank` | Tidak konsisten untuk label bank yang sama (masing-masing ada banyak kode). Contoh jumlah kode berbeda per bank: Bank BCA=171, Bank BNI=182, Bank BRI=170, Bank Mandiri=152 |
| `email` | Domain `example.com` dan local-part banyak mengandung tanda baca tak lazim; detektor terlalu ketat bisa melewatkan |

## Hal-hal yang tidak boleh disimpulkan

- `no_ktp` tidak bisa dibuktikan sebagai NIK valid hanya dari isinya karena panjangnya 14 digit; namun secara **makna kolom** ini adalah *kandidat identifier KTP* dan tetap perlu terlindungi.
- `nip_kppn` tampak seperti NIP individual, tetapi dump tidak menjelaskan pemiliknya. Jangan menganggap ini pasti NIP anggota DPR RI.
- `jumlah_anak` adalah jumlah anak yang dimiliki seseorang, **bukan data seorang anak tertentu**; tidak otomatis dikategorikan sebagai data pribadi spesifik menurut klausul data anak.
- `pekerjaan_terakhir = Dokter` adalah pekerjaan, **bukan riwayat kesehatan**.
- `nama_bank`, `nama_kppn`, dan `kode_bank` bukan bukti bahwa data satu baris aman dipublikasikan.
- CSV ini bukan policy encrypt semua kolom. Simpulkan teknik proteksi terpisah berdasarkan kebutuhan akses, pencarian, pencadangan dan retensi.

## Evaluasi yang dianjurkan

- Normalisasi nama kolom `public.anggota.nama` vs `anggota.nama` sebelum membandingkan, tetapi **jangan** menghapus atau mengganti kolom yang valid.
- Prediksi yang dibandingkan sebaiknya menggunakan kelas (`non-pribadi`, `umum`, `spesifik`) dan `is_personal` secara terpisah; gunakan confusion matrix, precision, recall, F1 macro/per class.
- Simpan kumpulan label ini terpisah dari kode serta aturan scanner agar tidak terjadi **data leakage ke evaluator**. Jika aturan dibangun dari semua label ini, laporkan hasil sebagai **in-sample** dan uji juga pada dataset sintetis held-out berlabel manual.
- Karena dataset hanya satu tabel dengan mayoritas atribut pribadi, metrik binary `is_personal` dapat tampak tinggi secara artifisial. Tampilkan confusion matrix multi-kelas dan uji di tabel non-pribadi/teks bebas tambahan untuk kualitas generalisasi.

## Referensi untuk README atau laporan

- Soal Final Hackathon DPR RI 2026, Tantangan 1.
- DPR RI Detail Hackathon, Persyaratan Teknis Wajib — Penemuan dan inventarisasi data.
- Onno W. Purbo (2026), *Data Leak-Proof: Teknik Proteksi Data di PostgreSQL agar Kebocoran Tidak Berarti Apa-Apa*, Bab 1.3, 2.7, 3.7.
- Onno W. Purbo, *Overview Serangan ke Data dan Database*, Bab 1–3.
- UU No. 27 Tahun 2022 Pasal 1 dan Pasal 4. https://jdih.komdigi.go.id/produk_hukum/view/id/832/t/crc32/
