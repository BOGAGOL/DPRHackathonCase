"""Local, read-only personal data candidate scanner."""

__version__ = "1.1.0"

CHANGE_SUMMARY = [
    "NIK nonstandar dengan bukti isi; kategori, tanggal pernikahan, hitungan keluarga, dan surrogate ID dibedakan.",
    "Sensitivitas dan dampak per jenis dari impact.yaml; tiga faktor lingkungan tetap terpisah.",
    "Functional dependency mengecualikan sumber hampir unik dan melaporkannya sebagai quasi-identifier.",
    "Turunan memakai review_minimization dan consistent_protection_with; rekomendasi nama/tanggal diperbarui.",
    "K-anonymity diurutkan minimal; superset berlebihan disembunyikan dan HTML dibatasi 15 kombinasi.",
    "Laporan memiliki tabel ringkas dan tata cetak A4 landscape.",
    "Evaluasi taksonomi independen melalui label_map.yaml, normalisasi kelas/boolean, F2, dan pengecualian kolom tidak berlabel.",
    "Kategori institusi memerlukan bukti isi; regex_only memakai kecocokan regex tanpa analisis relasi atau agregat k-anonymity.",
]
