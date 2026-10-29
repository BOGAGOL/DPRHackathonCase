# Triage secret scan S05

Gitleaks **8.30.1**, scan riwayat branch submission pada commit
`e6814fcef1636741d7785149715da53dde2beb44`, 29 Oktober 2026 WIB.
Scan sebelum triage selesai **21:54:35 WIB**; sesudah triage **21:56:08 WIB**.
Ini scan riwayat Git pada revisi tersebut, bukan pemeriksaan runtime atau janji
bahwa setiap string dalam seluruh filesystem aman.

| Kategori | Sebelum | Sesudah | Status dan alasan |
|---|---:|---:|---|
| Digest SHA-256 metadata berkas sumber | 34 | 0 | False positive. Nilai 64 digit heksadesimal merekam fingerprint sumber/manifest, termasuk nama `keys.py` di sebelah digest; bukan isi kunci. Fingerprint spesifik di-ignore. |
| Fixture kontrak `docs/contracts/test_vectors.json` | 1 | 0 | False positive. `search_key_hex` sintetis yang memang dipublikasikan untuk test vector lintas implementasi, bukan kunci lingkungan layanan. |
| Evidence unit pentest-kit | 1 | 0 | False positive. `app/evidence/access-control/pentest-kit-unit.json` memuat digest sumber `dpr-api.service` untuk provenance pengujian, bukan token/password. |
| `accounts.md` | 10 | 10 | Diterima dan didokumentasikan atas keputusan operator. Kredensial evaluator sengaja disediakan untuk juri mengakses demo berisi data sintetis; hak dibatasi RBAC. Bukan kunci kriptografi, token OpenBao, atau kredensial database. Akan dinonaktifkan setelah penjurian. **Tidak di-ignore.** |
| Total | 46 | 10 | 36 false positive, 10 temuan akun demo dalam riwayat. |

Sepuluh temuan riwayat akun berasal dari commit
`25617ba00300293f031f00c963ff04e4fee29a4d` dan
`e2d28f89ac42a8399f9df918dfacdec52c956b24`.
Jumlah temuan riwayat bukan jumlah akun unik saat ini. Tidak ada nilai kredensial
disalin di sini; `accounts.md` dipertahankan persis. Penerimaan akun demo tidak
berarti kredensial semacam itu layak dipakai pada deployment produksi.

`.gitleaksignore` disalin dari hasil triage lokal, UTF-8 tanpa BOM, berisi 36
fingerprint spesifik; **tidak ada fingerprint tambahan** dan tidak ada pengecualian
`accounts.md`. Kedua laporan menggunakan `--redact=100`; field `Secret` bernilai
`REDACTED` dan setiap `Match` memuat redaksi. Exit code kedua scan adalah 1 karena
temuan yang memang tetap harus dilaporkan.

Perintah yang dijalankan dari worktree submission:

```powershell
Move-Item .gitleaksignore .gitleaksignore.tmp
try {
    gitleaks detect --source . --config .gitleaks.toml --redact=100 --report-format json --report-path evidence/secrets/gitleaks-history.json
} finally {
    Move-Item .gitleaksignore.tmp .gitleaksignore
}
gitleaks detect --source . --config .gitleaks.toml --redact=100 --report-format json --report-path evidence/secrets/gitleaks-history-after-triage.json
```

**Kesimpulan S05 dalam scope scan dan triage ini:** 0 kunci kriptografi runtime,
token layanan, atau kredensial database/OpenBao teridentifikasi di repositori.
Kredensial layanan yang terdeteksi hanya akun evaluator yang sengaja disediakan;
fixture kriptografi sintetis tetap dibedakan dari rahasia runtime. Jangan menyebut
hasil sesudah triage sebagai "0 temuan".

Bukti: [sebelum triage](gitleaks-history.json),
[sesudah triage](gitleaks-history-after-triage.json),
[ignore spesifik](../../.gitleaksignore).
Pemeriksaan plaintext log S06 yang sudah ada: [plaintext-scan.json](plaintext-scan.json).
Evidence S06 tersebut tidak dijalankan ulang atau diubah pada pekerjaan ini.

## Scan final setelah perubahan remote

Fetch sebelum push menemukan remote submission maju ke
`0e505216e1cdc68a19581ff66a186ca845150def`. Lima commit pekerjaan ini direbase ke
remote tersebut tanpa konflik, sesuai instruksi operator. Karena kode yang masuk
dari remote menambah fitur refresh token, scan riwayat diulang pada revisi hasil
rebase **`d58a0210a8656e649d4a6bb4d044770ae5da5345`**. Scan pertama di atas tetap
dipertahankan; hasil final memakai file baru:

- [Sebelum triage final](gitleaks-history-final.json).
- [Sesudah triage final](gitleaks-history-final-after-triage.json).

Hasil final tetap **46 sebelum / 10 sesudah**, dengan kategori yang sama: 34 digest
metadata sumber, 1 fixture kontrak, 1 evidence unit pentest-kit, dan 10 temuan
riwayat akun evaluator. Tidak ada fingerprint baru dan tidak ada akun demo yang
di-ignore. Gitleaks tetap 8.30.1 dengan `--redact=100`, exit code 1 pada kedua scan.
Scan final selesai **29 Oktober 2026 22:10:29 WIB** sebelum triage dan
**22:12:16 WIB** sesudah triage, berdasarkan metadata kedua file laporan baru.
