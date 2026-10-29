# Struktur sumber dan paket pengumpulan

## Keputusan struktur

Satu aplikasi aktif `app/` dan satu jalur infrastruktur `infra/`. Prototipe PG17,
`apps/`, `infrastructure/`, `docker-compose.yml`, skrip root dan test lamanya
dihapus dari snapshot. Versi lama tetap tersedia pada commit `88b1de7` di Git;
dokumen/evidence lamanya ada di `archive/legacy-service/`, bukan bahan klaim terbaru.

Nama/path modul aktif dipertahankan karena dipakai deployment, import Python,
skrip acceptance dan pekerjaan anggota tim. Perapian tidak mengubah kontrak kripto,
skema data, target benchmark, isi database atau material kunci.

`docs/` diatur menurut kebutuhan pembaca: architecture, security, operations,
report, presentation, sbom dan submission. `evidence/` tetap memakai kategori
modul agar laporan lama tidak kehilangan rujukan. `results/`, `.venv/`, `node_modules/`,
`.next/` dan `.local/` adalah keluaran/lingkungan lokal, bukan sumber pengumpulan.

## Paket sumber

```powershell
python -m infra.submission sbom
python -m infra.submission check
python -m infra.submission build --output dist/submission
```

Gunakan folder output baru/kosong; build menolak menimpa paket lama. ZIP berisi
file sumber aktif, dokumentasi dan evidence yang dipilih, `SOURCE_MANIFEST.json`
dengan SHA256/ukuran per file, serta `QUALITY_REPORT.json`. Sesudah menulis ZIP,
tool memeriksa CRC dan membandingkan ulang seluruh hash isinya.

Pemilihan memakai allowlist root aktif ditambah denylist. Tidak cukup mengandalkan
`.gitignore`. Yang dikecualikan: dataset panitia, rahasia, kunci, file akun, dump,
backup terenkripsi, `.git`, cache/environment, arsip lama, dan referensi buku mentah.
File SQL hanya dipilih pada lokasi source skema/role yang direview. Link keluar
tree melalui symlink ditolak. Screen pola credential tidak menggantikan gitleaks
seluruh riwayat atau scan data pribadi/log.

Paket dapat berstatus `REVIEW_REQUIRED` meskipun struktur/hash/link lulus. Status
luaran ada di [checklist](CHECKLIST.md); ZIP sumber tidak menggantikan PDF laporan,
slide final, seri benchmark API yang belum lengkap, atau review manusia yang belum selesai.
Kumpulkan raw benchmark yang sah dari laptop pemiliknya secara terpisah setelah
review privasi; `results/` lokal tidak disalin otomatis.

## Setelah review branch

1. Tim meninjau diff, dokumen, kelas data, dan sumber angka.
2. Gabungkan perubahan anggota lain secara sadar; regenerasi SBOM/cek paket jika
   requirements, lockfile atau compose berubah.
3. Finalisasi PDF/slide dan samakan klaim dengan evidence beserta scope-nya.
4. Bekukan commit, build paket dari checkout bersih, catat SHA256 ZIP.
5. Upload hanya paket yang direview ke folder pengumpulan dengan akses juri yang benar.
   Jangan mengunggah seluruh folder kerja atau `.git`, karena riwayat repo private
   dapat memuat dataset panitia. Pengumpulan/upload tidak dijalankan tool ini.

## Launcher dan perapihan final 29 Oktober

Entry point baru `python -m infra.reproduce {setup,demo,verify,test}`;
[panduan tunggal](../operations/REPRODUCTION.md) menggantikan petunjuk quick-start
tersebar. Runbook modul dipertahankan untuk operasi terarah pada lingkungan existing.

Cache Python, build frontend usang bila tidak ada Node service berjalan, dan ZIP
lama dibersihkan; environment/dependency lokal tetap diabaikan paket. Nama source
modul dan seluruh raw/hasil numerik historis dipertahankan. Dua tautan Markdown
riwayat diperbaiki setelah perpindahan folder, tanpa mengubah hasil uji.

`accounts.md` dari main terbaru dikeluarkan dari snapshot dan disimpan privat.
Jangan memasukkannya kembali ke repo/lampiran. Riwayat Git masih memuat file itu;
rotation kredensial deployment bila masih berlaku menjadi tindakan operator.

Schema SBOM deklarasi/lock/image diregenerasi dan diverifikasi; BOM environment
serta audit lain tetap snapshot terpisah. Tidak ada ZIP baru dibuat pada tahap ini.
