# Scanner 1.2.0 dan evaluasi independen

Scanner membaca sampel dan agregat dalam transaksi REPEATABLE READ READ ONLY.
Hasil memuat contoh termasking, bukan salinan nilai sumber. Jalankan dari root repo
Windows PowerShell, gunakan venv scanner yang dependensinya dipin di `requirements.txt`.
Langkah 4 dibatasi pada database `postgres` (734 baris), bukan baseline 100k/1M.

## Credential dan test

```powershell
$cScannerSecure = Read-Host 'Password scanner_user lab' -AsSecureString
$cScannerCredential = [pscredential]::new('scanner_user', $cScannerSecure)
try {
  $env:SCANNER_DATABASE_URL = 'postgresql://scanner_user:' +
    [Uri]::EscapeDataString($cScannerCredential.GetNetworkCredential().Password) +
    '@127.0.0.1:5433/postgres?sslmode=disable'
} finally { Remove-Variable cScannerCredential,cScannerSecure }
$env:SCANNER_TEST_DATABASE_URL = $env:SCANNER_DATABASE_URL
.\scanner\.venv\Scripts\python.exe -m pytest scanner/tests -q
.\scanner\.venv\Scripts\python.exe -m pytest scanner/tests/test_detection.py -q -k disguised_names
```

Test integrasi hanya memeriksa snapshot read-only, isolasi transaksi, dan batas sampel;
tidak membuat/mengubah tabel. Jangan merotasi password role untuk mengulang pengujian.

## Scan dan evaluasi sesi 1.1 (historis)

Perintah pembuatan evidence berikut untuk eksekusi pertama. Pertahankan
`evidence/scanner/before_v1/` dan pilih direktori baru untuk scan ulang agar hasil lama tetap utuh.

```powershell
.\scanner\.venv\Scripts\python.exe -m scanner db --schema public --sample 1000 --label before --out evidence/scanner/before_v1_1
.\scanner\.venv\Scripts\python.exe -m scanner db --schema public --sample 1000 --label before --baseline regex_only --out evidence/scanner/before_regex_only
.\scanner\.venv\Scripts\python.exe -m scanner evaluate --pred evidence/scanner/before_v1/inventory.csv --truth scanner/ground_truth_eval.csv --out evidence/scanner/evaluation_v1.json
.\scanner\.venv\Scripts\python.exe -m scanner evaluate --pred evidence/scanner/before_v1_1/inventory.csv --truth scanner/ground_truth_eval.csv --out evidence/scanner/evaluation_v1_1.json
.\scanner\.venv\Scripts\python.exe -m scanner evaluate --pred evidence/scanner/before_regex_only/inventory.csv --truth scanner/ground_truth_eval.csv --baseline regex_only --out evidence/scanner/evaluation_regex_only.json
Remove-Item Env:SCANNER_DATABASE_URL,Env:SCANNER_TEST_DATABASE_URL
```

`config/label_map.yaml` hanya dipakai evaluator. Isi `ground_truth_eval.csv` dan
`docs/ground_truth_methodology.md` tidak diubah. Nama tabel tanpa schema dinormalisasi
ke `public`; label tipe dipetakan tanpa mengubah prediksi. `non-pribadi` sama dengan
`non_pribadi`; is_personal menerima 1/0, yes/no, true/false. Prediksi tambahan (`id`)
dicatat terpisah dan tidak masuk denominator; prediksi hilang tetap masuk denominator.
Label tidak terpetakan tampil eksplisit dan dihitung salah pada akurasi tipe.

Evaluasi gabungan menganggap setiap kandidat dengan kelas selain non_pribadi sebagai
personal, termasuk low_confidence. Regex_only mendeteksi personal jika tipe didukung
dan content_score >=60, dengan name_score=0; ambang ini ditetapkan di config sebelum
run, tanpa menyetel ulang dari hasil. Tidak cocok regex berarti tidak terdeteksi,
bukan bukti bahwa kolom non-pribadi. Analisis relasi dan agregat k-anonymity dilewati
pada mode regex_only untuk menjaga metode sederhana dan beban kecil. Akurasi kelas
PDP/tipe tetap dibandingkan terhadap prediksi mentah, terpisah dari keputusan biner.

Semua evaluasi berstatus **in_sample: true**. Ketidakcocokan dengan konvensi label
institusi tidak mengubah domain FIN `kode_bank` pada kontrak. Distribusi prioritas
memakai faktor lingkungan yang sama; baseline minimum P2, sementara konfigurasi after
memungkinkan P3. Nama/duplikat tidak di-hash atau dihapus otomatis. HTML menyediakan
ringkasan dan CSS cetak A4 landscape; seluruh kombinasi k-anonymity tetap ada di JSON.

Hasil sesi 27 Oktober 2026 ada di [comparison.csv](../evidence/scanner/comparison.csv),
[evaluasi v1.1](../evidence/scanner/evaluation_v1_1.json), dan
[validasi artefak](../evidence/scanner/step4_validation.json).
`evaluation.json` adalah salinan evaluasi v1.1. Seluruh 188 test, termasuk integrasi
read-only dan nama disamarkan, lulus; keputusan/keterbatasan terperinci ada di NOTES.md.

## Relasi v1.2 dan scan terbaru

Functional hanya dilaporkan jika seluruh grup konsisten (`consistent_group_ratio=1.0`)
dan rasio unik non-NULL sumber <=0.8. Kolom di atas batas dicatat sebagai
near_unique_quasi_identifiers. Komponen setelah koma terakhir dapat diuji terhadap
kolom lain; kecocokan persis pada seluruh pasangan dicatat sebagai `text_component`.
Dengan demikian relasi alamat → kota dibuktikan dari komponen yang cocok, sementara
alamat unik tetap dikecualikan sebagai sumber functional. Nama kolom tidak di-hardcode.
Presence iff kategori tetap dianalisis dengan seluruh pasangan, termasuk NULL.

Setelah mengatur env scanner dengan aman seperti di atas, untuk eksekusi pertama:

```powershell
.\scanner\.venv\Scripts\python.exe -m scanner db --schema public --sample 1000 --label before --out evidence/scanner/before_v1_2
.\scanner\.venv\Scripts\python.exe -m scanner evaluate --pred evidence/scanner/before_v1_2/inventory.csv --truth scanner/ground_truth_eval.csv --out evidence/scanner/evaluation_v1_2.json
Get-Content -Raw evidence/scanner/before_v1_2/relations.json | ConvertFrom-Json
```

Pertahankan keluaran historis; gunakan direktori berbeda untuk scan ulang.
Hasil aktual v1.2: [evaluasi](../evidence/scanner/evaluation_v1_2.json) dan
[validasi relasi/test](../evidence/scanner/v1_2_validation.json).
