# 6. Bahan tanya jawab

Jawab langsung, sebut scope, lalu buka backup/evidence bila diminta. Tidak perlu
membacakan semua detail sebelum pertanyaan. Jawaban berikut adalah konteks yang
harus disesuaikan pembicara, bukan tanda semua masalah telah selesai.

## 1. Apa risiko utama yang diselesaikan?

Salinan plaintext membuka identitas/keuangan tanpa login aplikasi. Kami mengurangi
pemulihan field sensitif dari salinan protected, lalu mengukur sisa informasi dan
biaya layanan. Kami tidak mengklaim mencegah semua pencurian database. S01–S04.

## 2. Mengapa PostgreSQL, padahal studi kasus menyebut MySQL?

Soal final mengizinkan PostgreSQL dengan adaptasi dump yang dijelaskan dan
pelestarian fungsi/hubungan data. Sumber hanya INSERT tanpa DDL, sehingga tim
membentuk schema dan menjaga NULL, string identifier serta nol awal. Benchmark
membandingkan PostgreSQL plain/protected, bukan efek pindah engine. cadangan A01.

## 3. Mengapa tidak mengenkripsi semua kolom?

Kontrol dipilih menurut risiko dan kegunaan.25field AEAD,4 REF dan age_band
turunan dipakai untuk kebutuhan statistik. REF/pola NULL tetap surface inferensi
yang diukur; keputusan itu bukan pernyataan REF aman dipublikasikan per record.
Tiga nama identik belum dihapus karena kontrak mempertahankan kolom. S03/A02.

## 4. Mengapa kode_bank ikut FIN?

Nilainya pada sumber tidak konsisten sebagai kode institusi biasa dan menjadi
proxy ketika digabung atribut lain. Label acuan jenis nilainya non-pribadi,
namun hubungan dengan orang tetap berisiko. Kelas hukum, risiko dan domain
kripto adalah keputusan berbeda. Review manusia masih diperlukan. cadangan A01.

## 5. Apakah 0% berarti seluruh data tidak berguna bagi penyerang?

Tidak. 0% adalah ESCE untuk 25 kolom AEAD non-NULL pada artefak tanpa key yang
diperiksa. REF, NULL, panjang, equality dan legacy mapping masih terlihat.
Sumber 734 masih k=1 pada proyeksi tertentu. Jangan menyebut 0% semua leakage. S04.

## 6. Jika capability finansial bocor, apakah identitas tetap aman?

PII AEAD tidak terbuka melalui policy FIN pada probe. Tetapi FIN sendiri memuat
rekening, NPWP dan nama rekening, sehingga identifier tetap dapat terungkap;
DIE pada simulasi tersebut 100%. Pemisahan domain membatasi dekripsi, bukan
menjamin identitas tidak bisa direkonstruksi. cadangan A02.

## 7. Apakah yang disebut “key bocor” benar-benar KEK diekspor?

Model uji memakai capability/policy yang dapat memanggil operasi domain tertentu.
Itu tidak harus berarti byte KEK mentah diekspor. Sebut jenis capability dan ACL
probe, jangan menggambarkan semua skenario sebagai pencurian file KEK. A02/A04.

## 8. Bagaimana jika aplikasi dan akses Bao dikuasai bersamaan?

Kerahasiaan field yang dapat didekripsi proses tersebut tidak lagi dijamin.
svc-app memang memiliki kemampuan PII dan FIN; backend menegakkan role HTTP dan
field. Key-plane tidak otomatis mengetahui bahwa endpoint hanya boleh PII.
Pemisahan tugas, TTL/revokasi, audit dan pembatasan respons mengurangi risiko. A04.

## 9. Blind index apakah aman dari tebakan?

HMAC menghindari hash identifier tanpa kunci dan menjaga key di Bao. Namun
equality/frequency tetap bocor; capability search dengan kamus dapat memulihkan
nilai. Simulasi memakai kamus sintetis lengkap sebagai batas atas dan memulihkan
sekitar 12,24%sel AEAD, tanpa mendekripsi AES. Ini tradeoff exact search. A02/A04.

## 10. Mengapa AAD diperlukan?

Tag AES-GCM mengautentikasi ciphertext bersama AAD. Format v1 mengikat nama kolom,
UUID record dan protection_version. Bit tamper atau pemindahan ke record/kolom
lain gagal tertutup. Ini tidak otomatis mencegah delete atau rollback seluruh
snapshot database ke versi lama. cadangan A04.

## 11. Apakah UUID membuat dataset anonim?

Tidak. UUIDv4 mengurangi ketergantungan id berurutan dan menjadi bagian AAD,
tetapi legacy_row_id masih memetakan sumber. Atribut lain juga dapat membantu
inferensi. API B memakai business id yang dipetakan dan scope tetap diperiksa.
Jangan menyamakan pseudonimisasi dengan anonimitas. A02/A04.

## 12. Analyst count>=5 berarti sudah k-anonymous?

A5 hanya merilis lima marginal satu dimensi dengan count>=5. Kelompok kecil
tidak mengeluarkan label; total API null. Itu bukan k-anonymity kombinasi semua
REF, bukan differential privacy, dan tidak menjamin tahan differencing antarwaktu.
Raw table/view per record tetap ditolak untuk analyst_user. S05/A02.

## 13. Bukankah RLS cukup untuk mencegah pencuri credential?

RLS memakai principal yang di-set per transaksi. Pemegang credential app_user
dapat mengubah setting tersebut. Karena itu query scope dan otorisasi backend
tetap utama; RLS membantu pertahanan berlapis terhadap kesalahan, bukan batas
identitas kuat terhadap pencuri role tersebut. S03/A04.

## 14. Apakah DEK disimpan atau cache aktif di aplikasi?

DB menyimpan wrapped DEK, DEK plaintext dipakai di memori. Toolkit mempunyai
kemampuan cache default 15 detik, tetapi konfigurasi app saat ini dan benchmark v2
cache OFF. Python/OS tidak menjamin zeroization seluruh salinan atau swap.
Jika cache diaktifkan, revokasi bisa terlambat hingga sisa TTL. cadangan A04.

## 15. Mengapa performanya jauh lebih lambat?

Hasil mengandung query, crypto, RPC HMAC/unwrap dan transport/key service.
Diagnosis menunjukkan mean SQL jauh lebih kecil daripada mean client untuk
contoh lookup; selisih bukan bukti seluruhnya AES atau satu penyebab tertentu.
Tujuan kami melaporkan biaya dengan jujur. P01/P01A/P02 gagal; P03 error lulus.
Perbaikan tetap diperlukan sebelum mengusulkan SLA instansi. S06/A03.

## 16. Mengapa v2 membaik jika HTTPX lama sudah keep-alive?

Perubahan transport mengurangi overhead jalur dispatch/session dengan pool
eksplisit; HMAC batch juga ditambahkan untuk operasi yang sesuai. Kami tidak
mengklaim sebelumnya selalu handshake setiap request. Perbandingan naive/v2
adalah antarsesi dengan metadata, bukan isolasi kausal satu faktor. cadangan A03.

## 17. 38,62 ms itu respons aplikasi di VM?

Tidak. Itu median p95 per-run lookup NIK pada benchmark DB adapterv2 untuk 1M.
API comparison masih PLANNED pada snapshot. Jangan memindahkan metrik DB ke
HTTP endpoint, UI browser, hardware VM atau semua skenario. S06.

## 18. Apakah ulangan dan targetnya ditetapkan sebelum run?

Sesi DB naive/v2 masing-masing 112 run untuk dua skala, dua blok B-P-P-B dan
empat run per mode/skenario. Target commit 8c09a25 mendahului run dan tidak
dilonggarkan sesudah hasil. Rencana API yang dikurangi menjadi dua ulangan belum
memenuhi minimum awal tiga dan belum mempunyai hasil pada snapshot ini. A03.

## 19. Bukti layanan bekerja apa, selain unit test?

Lab terisolasi memakai PG 18/OpenBao TLS/API/Next/Chrome nyata,143 checks pada17 record
buatan tim, termasuk recovery. Web deployment100 checks/enam akun adalah scope
lain. Operator B juga mempunyai bukti A5 SQL dan satu reset VM65 smoke, tetapi
bukan full pentest. Angka tersebut tidak dijumlahkan menjadi satu sertifikasi.
S05/A06.

## 20. Mengapa bukan restore live saat presentasi?

Restore/migrasi/rotasi berisiko menghabiskan waktu dan mengubah sistem yang
sedang dipakai. Demo menggunakan read-only anggota pada lingkungan berizin,
sedangkan integrity/restore ditunjukkan dari hasil nyata sebelumnya dengan
label yang jujur. Bukti lab tersedia; tidak berpura-pura itu operasi live. Bab4.

## 21. Jika Bao hilang, apakah backup DB cukup?

Tidak. Perlu material key-plane yang cocok, kunci enkripsi backup dan HMAC,
custody/recovery, role dan sertifikat sesuai kebutuhan. Membuat pii-kek baru
dengan nama sama tidak membuka wrapper lama. Unseal volume existing dan restore
data tidak membuktikan DR seluruh key-plane pada mesin baru. cadangan A05.

## 22. Data terhapus apakah sudah hilang dari semua backup?

Drill membuktikan anggota buatan pada clone tidak muncul di backup baru setelah
delete. Backup lama tetap memuatnya sampai masa retensi berakhir. Deadline
retensi bukan scheduler purge atau bukti secure erase seluruh SSD/salinan.
Tidak ada klaim penghapusan fisik menyeluruh. cadangan A05.

## 23. Bagaimana rotasi dilakukan?

Rotate pii-kek lalu rewrap DEK wrapper tanpa mengenkripsi ulang field. Checkpoint
dan compare-and-swap membantu resume tanpa menimpa perubahan. Lab Alby membuktikan
100.734 wrapper PII v1 → v2 tetap terbaca; bukan rotasi 1M/semuaVM, FIN atau search
otomatis. Versi lama tetap diperlukan untuk arsip lama. cadangan A05.

## 24. Apakah log, filesystem dan seluruh Git history sudah bersih?

Ada pemeriksaan keluaran tertentu dan sanitasi evidence, tetapi audit final
menyeluruh terhadap secret/history/log/temp/screenshot belum lengkap. Enkripsi
field/dump tidak membuktikan physical file/WAL/log aman. Ini gap yang dinyatakan,
bukan PASS yang disimpulkan dari tidak ditemukannya masalah pada unit test. S08.

## 25. Mengapa masking tampilan berbeda dari contoh panitia?

Toolkit menyediakan format contoh, sedangkan runtimeB memakai variasi masking
yang menyembunyikan bagian berbeda; peran tertentu memang mendapat nilai sah
lengkap. Gap kesamaan format perlu keputusan tim dan retest bila diubah. Jangan
merekayasa screenshot agar tampak memakai fungsi yang sebenarnya tidak dipakai.
cadangan A06.

## 26. Berapa biaya, RPO/RTO dan kesiapan produksi?

Belum ada angka produksi tervalidasi. Storage1M sekitar 2,679× pada snapshot,
dan performa DB mempunyai overhead yang diukur. Instansi perlu menilai topologi,
latensi Bao, kapasitas/WAL/backup/clone, operator, custody, audit dan pengukuran
RPO/RTO. Prototipe bukan sertifikat patuh UU PDP atau produk HA siap operasi. S07–S08.

## 27. Penggunaan AI dan review manusia bagaimana?

AI membantu implementasi, test, audit dan penulisan. Evidence otomatis tidak
menggantikan reviewer kelas data/risiko, review klaim dan persetujuan final.
Jangan mengisi nama/approval yang belum diberikan. Dokumentasi dan kode tetap
mengikuti lisensi masing-masing; dataset panitia tidak dipublikasikan. S08/A06.
