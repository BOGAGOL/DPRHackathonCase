# Matriks risiko dan perlakuan data

[risk-matrix.csv](risk-matrix.csv) memuat **29 kolom sumber**, dibentuk dari
`policy/protection_profile.yaml` dan inventory scanner yang dirujuk provenance-nya.
CSV berisi nama atribut, kelas/risiko/priority scanner, domain dan kontrol; tidak
memuat nilai anggota atau contoh lengkap. Ini bukan keputusan final reviewer manusia.

## Cara membaca

- `scanner_risk`, `scanner_priority`, `scanner_score`: penilaian awal scanner,
  dipertahankan dari inventory, bukan skor residual yang diukur setelah mitigasi.
- `domain`, `storage`, `blind_index`, `normalization`: keputusan teknis kontrak/profile.
- `analyst_projection`: proyeksi yang ditetapkan profile; `analyst_release`:
  REF/age_band hanya dapat dirilis sebagai marginal count>=5;
  bukan SELECT per record untuk analyst_user.
- `reason`: alasan keputusan tim pada profile; `review_status` masih NEEDS_REVIEW.
- Risiko sisa umum: equality pada blind index, REF/pola NULL, aplikasi+key plane
  kompromi, role credential theft dan backup lama; lihat [keterbatasan](LIMITATIONS.md).

Nama lengkap, KTP-like, alamat/kontak, keluarga dan agama masuk domain PII;
rekening/nama rekening/NPWP/kode bank masuk FIN. `kode_bank` dilindungi meski
metadata institusi, karena pola sumber dapat menjadi proxy identitas. Umum/spesifik
tidak sama dengan domain kripto; agama diperlakukan berisiko tetapi bukan otomatis
kelas data spesifik. `jumlah_anak` bukan bukti data seorang anak tertentu.

Skala risiko sebelum proteksi berasal dari konfigurasi/scoring scanner pada
populasi uji. Tim perlu mereview kegunaan, volume, exposure, exploitability,
impact dan recovery pada lingkungan instansi yang sebenarnya; angka prototipe
tidak boleh disalin menjadi penilaian risiko produksi tanpa assessment baru.

Sumber dan kewenangan: [kontrak](../contracts/CONTRACT.md),
[profile](../../policy/protection_profile.yaml),
[metodologi ground truth](../ground_truth_methodology.md). Tidak mengubah domain,
normalisasi atau protection_version sebagai bagian dari penulisan matriks ini.
