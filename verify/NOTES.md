# Modul C — konfigurasi verifikasi

Keputusan tim 27 Oktober 2026: dataset panitia `sql/baseline/02_data.sql` boleh
di-commit hanya di repo PRIVATE. Repo tidak boleh dibuat public. Pengecualian S06
ada di `scan_config.toml`, hanya pencocokan path relatif persis setelah normalisasi
pemisah Windows menjadi `/`; bukan pengecualian seluruh folder atau semua SQL.
Gitleaks memiliki regex path berjangkar yang sama. Paket lampiran publik memakai
`export-ignore` di `.gitattributes`; pembuat paket lain wajib membaca daftar pengecualian.

Konfigurasi ini disiapkan sebelum runner S05/S06 diimplementasikan. Test memeriksa
kesesuaian ketiga konfigurasi dan menolak perluasan path yang tidak diminta; belum
merupakan hasil scan repo/riwayat/log. Runner nanti wajib memakai konfigurasi ini
dan merekam pengecualian di evidence, tanpa mengklaim path tersebut telah dipindai.
Known-values/snapshot/credential tetap privat di luar repo. Sumber DB `postgres`
dan hasil benchmark baseline_100k tidak diubah.
