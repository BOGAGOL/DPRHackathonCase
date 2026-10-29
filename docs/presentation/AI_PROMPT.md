# Prompt untuk AI pembuat slide

Buat rancangan presentasi Tim BOGAGOL berdasarkan CONTEXT.md, deck_plan.json,
evidence_cards.json, tables/ dan assets/ pada folder ini. Materi berasal dari
implementasi/evidence proyek, bukan klaim semua persyaratan telah lulus.

Audiens: juri teknis dan pemangku kepentingan instansi. Fokus wajib:
**risiko utama, prioritas solusi, bukti pelindungan, dampak kinerja, dan tahapan
penerapan di instansi**. Gunakan delapan slide utama yang disarankan, ditambah
enam backup bila diperlukan. Itu rancangan awal, bukan jumlah slide wajib panitia.

Siapkan inti300 detik tanpa demo live, serta versi840 detik termasuk demo240 detik
dan buffer60 detik hingga maksimum15 menit. Q&A sampai10 menit terpisah. Jika rundown
panitia berbeda, sesuaikan waktu dengan tetap meliputi kelima pokok.

Tulisan layar harus ringkas, satu pesan per slide. Pindahkan detail ke speaker
notes, tetapi **batas yang mengubah kesimpulan wajib terlihat di layar**:
ESCE hanya25 field AEAD, scope lab, DB bukan API, dan target performa gagal.
Tuliskan unit, skala, jumlah ulangan dan sumber singkat di caption/footnote.
Gunakan tabel/grafik yang dapat diedit dan diagram asli yang disediakan; jangan
mengganti data dengan gambar dekoratif atau screenshot UI yang direkayasa.

Aturan faktual:

1. Jangan membuat hasil API, screenshot/rekaman demo, approval reviewer, atau hasil
   deployment/DR/pentest yang tidak ada. Tandai rencana/demo yang belum disiapkan.
2. Jangan menulis “0% kebocoran seluruh data”, “100% aman”, “semua target lulus”,
   atau “identitas seluruhnya aman ketika key FIN bocor”.
3. P95, throughput dan target harus berasal dari pasangan B/P pada sesi DB yang sama.
   Optimasi naive→v2 adalah perbandingan antarsesi dan tidak membuktikan satu faktor
   penyebab. Tampilkan status gagal target walaupun latensi membaik.
4. Jangan menjumlahkan143lab+100web+31SQL+65reset menjadi satu sertifikasi atau
   jumlah pengguna/record. Semua scope harus tetap berbeda.
5. Analis hanya lima marginal count>=5, total=null, tanpa label kelompok kecil.
   Itu bukan differential privacy atau anonimisasi dump.
6. Cache app dan DB v2 OFF. Default toolkit15detik tidak berarti app memakai cache.
7. Semua credential/key/token/cookie/URL berpassword/nilai anggota lengkap dilarang
   masuk slide, notes, screenshot, video atau lampiran. Gunakan record buatan tim
   pada demo yang diizinkan, bukan memublikasikan sumber panitia lewat browser.
8. Masking runtime B berbeda dari format toolkit/panitia. Jangan memalsukan UI atau
   mengklaim seluruh tampilan memakai contoh yang sama.
9. Jangan memakai logo DPR/branding pemerintah seolah sistem resmi; gunakan identitas
   tim dan atribusi yang benar. Jangan mengarang angka biaya/SLA produksi.

Setelah membuat deck, periksa semua slide secara visual, latihan dengan timer,
periksa catatan sumber dan data tersembunyi, lalu minta review manusia. Jangan
menganggap kelengkapan konteks ini sebagai bukti PPTX/PDF final sudah dibuat.
