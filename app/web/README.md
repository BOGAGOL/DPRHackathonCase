# Frontend Modul B

Next.js App Router / TypeScript / Tailwind; satu-satunya frontend aktif berada di folder ini. Untuk alur lengkap gunakan [panduan reproduksi](../../docs/operations/REPRODUCTION.md). Semua browser request menggunakan origin yang sama (`/api`) dan DTO backend; frontend tidak melakukan keputusan otorisasi terhadap nilai lengkap yang disembunyikan. Nilai tidak disimpan di localStorage/sessionStorage.

PowerShell dari `app/web`:

```powershell
npm ci
# Backend harus sudah siap. Gunakan origin yang sama untuk plain dan protected benchmark.
$env:API_INTERNAL_URL = 'https://127.0.0.1:8100'
npm run build
# Isi path dari material TLS Modul A; tidak menyalin private key ke repo.
$env:TLS_CERT_FILE = Join-Path $env:DPR_SECRETS_DIR 'tls/server.crt'
$env:TLS_KEY_FILE = Join-Path $env:DPR_SECRETS_DIR 'tls/server.key'
$env:WEB_PORT = '3443'
npm start
```

Buka `https://localhost:3443/login`. Percayai CA lokal Modul A pada browser. Set `NODE_EXTRA_CA_CERTS=<path CA Modul A>` sebelum menjalankan Node; tidak ada `NODE_TLS_REJECT_UNAUTHORIZED=0`. `server.mjs` menolak start tanpa key/cert dan tidak fallback HTTP. Proxy API hanya menerima backend HTTPS. `API_INTERNAL_URL` dibaca saat runtime; tidak berisi kredensial. Isi `$env:NODE_EXTRA_CA_CERTS = Join-Path $env:DPR_SECRETS_DIR 'tls/ca.crt'` sebelum `npm start`.

CSP menggunakan nonce acak baru per request melalui `src/proxy.ts`, `script-src` nonce/strict-dynamic, `style-src` nonce, `frame-ancestors 'none'`, tanpa unsafe-inline/unsafe-eval. Root layout force-dynamic agar nonce tidak tercache. Gunakan build produksi untuk demo; HMR development tidak menjadi bukti CSP produksi.

Enam peran: operator/privileged_officer/finance_officer/anggota menuju daftar anggota; analyst hanya analytics; auditor hanya audit. Backend tetap memeriksa seluruh record/field. Form kontak hanya mengirim nilai pengganti email/handphone. Pencarian GET KTP/email memakai fetch, bukan navigasi URL. Custom route proxy menangkap kegagalan upstream tanpa mencetak URL/query, tidak mengikuti redirect, serta meneruskan cookie/CSRF/origin dan no-store. ID layanan adalah string stabil `legacy_row_id` di kedua mode; UUID kripto protected tidak dikirim ke browser.

Verifikasi:

```powershell
npm run build
# Menggunakan API tiruan sintetis, tanpa password/token statis atau DB asli.
npm run test:ui
node scripts/summarize-ui.mjs
```

Ringkasan mesin tersanitasi ditulis ke `app/web/evidence/access-control/ui-tests.json`. Raw report dan test artifacts hanya `.local`, diabaikan Git. Tes UI melengkapi pengujian backend. Pengujian dengan mock tidak membuktikan TLS DB, integrasi OpenBao, atau matriks otorisasi backend. `scripts/live-probe.mjs` menerima konfigurasi/credential melalui stdin dari runner integrasi, memeriksa enam peran lewat HTTPS nyata dan browser dengan pin SPKI sertifikat lab; tidak mencetak credential atau body respons.
