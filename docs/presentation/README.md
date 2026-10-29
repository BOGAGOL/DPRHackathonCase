# Paket konteks presentasi — Tim BOGAGOL

Disusun 29 Oktober 2026 WIB pada branch `chore/submission-polish`, menggunakan
konteks/evidence laporan yang diperbarui sampai commit `f54adf5`.
Ini bahan untuk AI pembuat slide dan pembicara, **belum PPTX/PDF atau rekaman demo**.
Seluruh bahan baru untuk presentasi berada di folder ini.

## Untuk diberikan kepada AI lain

Berikan **[CONTEXT.md](CONTEXT.md)** dan **[AI_PROMPT.md](AI_PROMPT.md)** terlebih
dahulu. CONTEXT menggabungkan semua bab bahan presentasi. Sertakan `assets/` dan
`tables/` bila AI juga membuat visual. Tidak perlu mengirim seluruh repo, raw,
credential demo, atau file privat.

| Berkas | Isi |
|---|---|
| [01_BRIEF_DAN_ALUR.md](01_BRIEF_DAN_ALUR.md) | Lima pokok soal, audiens, delapan slide utama, waktu dan sumber persyaratan |
| [02_ISI_SLIDE.md](02_ISI_SLIDE.md) | Teks layar, pesan, visual, bukti, footnote dan enam slide cadangan |
| [03_NASKAH_PEMBICARA.md](03_NASKAH_PEMBICARA.md) | Narasi inti lima menit dan tambahan untuk versi panjang |
| [04_DEMO_DAN_CADANGAN.md](04_DEMO_DAN_CADANGAN.md) | Demo empat menit yang disiapkan operator, privasi, preflight, fallback |
| [05_BUKTI_DAN_VISUAL.md](05_BUKTI_DAN_VISUAL.md) | Angka terpilih, spesifikasi grafik, sumber, unit dan batas klaim |
| [06_TANYA_JAWAB.md](06_TANYA_JAWAB.md) | Jawaban teknis/nonteknis beserta batas yang harus disebut |
| [07_CHECKLIST_FINAL.md](07_CHECKLIST_FINAL.md) | Pekerjaan manusia sebelum deck dibekukan dan dipresentasikan |
| [deck_plan.json](deck_plan.json) | Timing 300 detik inti,840 detik versi panjang termasuk 240 detik demo,60 detik buffer |
| [evidence_cards.json](evidence_cards.json) | Data terpilih, sumber asli dan batas setiap klaim |
| [source_manifest.json](source_manifest.json) | Hash sumber data, narasi dan aset yang dipakai |

## Status hasil yang harus tetap terlihat

- Bukti dump tanpa kunci: ESCE 0% untuk 25 kolom AEAD non-NULL yang diperiksa;
  bukan nol seluruh informasi/inferensi.
- FIN/search capability bocor masih dapat mengungkap identifier; sumber 734 masih k=1.
- DB naive/v2 telah diukur, tetapi **gagal P01/P01A/P02**, **lulus P03**.
- API masih **PLANNED** pada snapshot; tidak mengisi angka API dari benchmark DB.
- Lab 143 checks/17 record, web100 checks/enam akun, SQLA5 dan reset VM adalah bukti berbeda.
- Tidak ada klaim full pentest, kepatuhan hukum, audit log/history penuh atau DR
  seluruh key-plane yang belum dibuktikan.

Regenerasi metadata/gabungan: `python docs/presentation/build_context.py`.
Pemeriksaan: `python docs/presentation/verify_context.py`, kemudian
`python -m pytest docs/presentation/tests -q`.
Tool hanya membaca metadata dan menulis folder presentasi; tidak menghubungi VM,
memakai akun, menjalankan benchmark, atau membuat deck/ZIP.
