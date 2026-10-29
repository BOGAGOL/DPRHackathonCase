# Progres Modul B — 28 Oktober 2026

## Revisi A5/B4

Implementasi mengikuti CONTRACT 10.1/PR A #10, hanya perubahan source di app/.
Analytics membaca public.analyst_summary sebagai analyst_user. Kelompok 1–4 dan
labelnya dihilangkan; count integer >=5 dan total selalu null. Filter cohort lama
ditolak 422; UI hanya memilih dimension/value marginal yang sudah dirilis.
Tidak ada fallback per-record/role atau decrypt analytics. Fixture dua mode dan
skrip integrasi disesuaikan; setup lab existing tidak dijalankan.

Build Next.js dan 14 test browser lulus. Test khusus analytics 64 lulus. Regresi
backend final 328 lulus/1 skip, termasuk gate readiness A5. Hasil mesin dicatat di
app/evidence/access-control/unit-tests.json dan analytics-a5.json.
Fixture SQLite/mocked UI bukan validasi SQL A5 pada VM.

VM menurut log pengguna: PostgreSQL/OpenBao TLS, migrasi 734, verifier A, provisioning
enam akun, backend/web HTTPS dan login operator sudah berhasil. Angka 2 pada akun
staf berasal dari default assignment 1,2. Perintah perluasan ke 734 sudah diberikan;
hasil eksekusinya belum diterima. Jangan menandai scope 734 PASS tanpa hasil itu.

Berikutnya: rilis paket baru dan SQL A5 ke VM sesuai docs/DEPLOY_A5.md; terima evidence
apply/verify dan acceptance akun. Jangan mengubah pg-dpr/baseline/target benchmark
Delf. VM A5, benchmark resmi, dan systemd tetap belum selesai/NOT TESTED.


## Perbaikan UI filter analytics

Sesuai screenshot Zhafif: ganti class tombol yang tidak ada dengan Button shared,
padding isi kartu, grid responsif, label eksplisit dan focus keyboard, tombol
Terapkan/Reset dengan hierarki jelas. Hapus teks berulang dan kartu total kosong.
Build Next/TypeScript lulus; Playwright 14 lulus, termasuk ukuran klik >=44px,
padding field, filter/reset, dan layout 320/390px tanpa overflow. Screenshot fixture
sintetis desktop/mobile di app/web/.local/ sudah diperiksa visual. Tidak ada perubahan
backend/SQL; pengujian Python tidak diulang untuk patch frontend ini.

Update VM belum dilakukan. Paket app/.local/dpr-analytics-ui.tar hanya frontend;
ikuti docs/DEPLOY_ANALYTICS_UI.md, hentikan web, extract/build, jalankan web lagi.
Backend, akun dan database tidak perlu diprovision/migrasi ulang. Systemd tetap
pekerjaan deployment terpisah.


## Penghapusan elemen UI yang ditandai

Panel promosi login diganti form ringkas di tengah. Kartu keamanan/sidebar footer,
indikator sesi, dan catatan teknis backend pada profil dihapus. CSS tak terpakai ikut
dibersihkan; header masih menampilkan akun/peran dan logout. Build dan 14 test browser
lulus, preview login desktop/mobile diperiksa. VM belum diperbarui otomatis; paket
app/.local/dpr-analytics-ui.tar kini memuat perubahan ini beserta perbaikan filter.
Gunakan lagi docs/DEPLOY_ANALYTICS_UI.md; cukup rebuild dan restart frontend.

## Persiapan whitebox pentest — 28 Oktober 2026

- IMPLEMENTED:8 akun pt terpisah, dua scope operator disjoint5+5, dua owner dengan
  pengguna_bidx unik; role lain sesuai ACCESS_MATRIX, private600, idempotent verify,
  satu perintah disable berikut invalidasi sesi. Tidak provision/rotate demo.
- IMPLEMENTED: login-only6 demo + read-only pt policy/IDOR/A5 smoke; inventory
  metadata runtime tanpa environment/token/body. Output manual VM tersimpan
  vm-inventory-operator.json, dengan cloud SG dan unknown36577 belum terverifikasi.
- IMPLEMENTED: dua unit systemd DPR dan launcher environment minimum; installer
  menolak proses foreground yang masih memakai port dan unit bukan milik kit.
- IMPLEMENTED: template protected_734_golden, audit private export, guarded reset
  fixed target, cluster/OID identity/role/TLS/RLS/A5 checks, post-restore14 login.
  Restore utama tetap Alby, golden bergantung pada key plane/versi Bao.
- DOCUMENTED: docs/deploy/PENTEST_BRIEF.md D1–D12, app/docs/PENTEST_SETUP.md,
  scripts/deploy helpers sesuai tambahan scope eksplisit pada prompt revisi.
- TESTED LOCAL:390 passed,1 skipped (suite backend lengkap);4 Bash syntax checks,
  wrong-target/unknown-action refusal,4 CLI help checks. Fixture sintetis/FakeCrypto
  dan fake katalog, bukan operasi DROP/CREATE PostgreSQL18 nyata.
- VM PASSED: operator menjalankan provision8 pt, dua unit enabled/active, A5verify,
  inventory, golden-create dan **satu reset nyata**. Raw metadata diunduh via SCP;
  vm-golden-reset.json passed:true, reset_test_statusPASSED, members734,
  smoke.accounts_checked14/demo_login_roles6 dan seluruh checkstrue. Private audit
  export7849 event; tidak ada nilai anggota/password di evidence publik.
- VM CONFIRMED: sourcepostgres734 migratedvalidated734, PG18.6/TLS dan MODEprotected,
  app_user/analyst_user/auditor_user verify-full; runtime Node24.22.1/Python3.12.3/
  Nginx1.24.0/Bao2.5.5. Peta akun/UUID aktual dan D1–D12 ada di brief. Unknown36577
  telah teridentifikasi containerd, excluded bersama tat_agent dan OS services.
- NEXT: pentest Delf memakai pt, hasil disimpan terpisah; primary restore Alby,
  disable pt setelah restore akhir. Cloud SG, custody kunci dan renewal penuh tetap
  belum dikonfirmasi. Jangan benchmark/migrasi laptop pg-dpr.

## Target clone benchmark — 29 Oktober 2026

- IMPLEMENTED: exact opt-in DPR_BENCHMARK_DATABASE untuk api_ clone di kedua MODE,
  same-target semua URL, role/CA/verify-full dan pemisahan recovery tetap berlaku.
- IMPLEMENTED: setup schema/provision mendukung clone sesuai MODE; setup CONNECT/
  USAGE/marker terbatas; startup read-only mengecek user/TLS/schema/owner/FORCE RLS.
- TESTED:437 passed,1 skipped backend;47 tes baru target/env/setup/provision/gate.
  Fixture sintetis/mocked metadata, tanpa koneksi benchmark atau database tim.
- HANDOFF: app/docs/BENCHMARK_CLONES.md. C harus mengirim env baru ke child process,
  mengarahkan seluruh URL dan CLI ke clone, memakai CA file di loader dan memastikan
  recovery cleanup sebelumnya selesai. Tidak mengubah benchmark/ atau infra/.
- NOT TESTED: clone PostgreSQL18 nyata, pengukuran API/performa dan C integration.
  VM demo tetap menggunakan konfigurasi existing; belum ada deployment patch ini.
- WORKTREE: fix/service-b-benchmark-targets, terpisah dari merge root pengguna.

## Upgrade dependency — 29 Oktober 2026

- PASS lokal: toolkit108/1skip, vector kontrak8, backend437/1skip, pip check bersih.
- cryptography50.0.2 dan pytest9.0.3 pada environment pengujian baru.
- First-party requirements diselaraskan; data, akun, format crypto tidak diubah.
- VM awal46.0.7/9.0.2, services active, deployment arsip tanpa Git.
- PENDING: penerapan VM, smoke65/14akun dan SBOM/audit environment final.

## Dependency release — hasil VM dan SBOM terkonfirmasi

Main merge4fdd7aa dipush; VM memakai arsip source terverifikasi159file karena
instalasi existing tanpa Git. Commit awal null/unknown; commit_after adalah
identitas manifest rilis, bukan klaim git checkout atau penggantian build frontend.
Selesai29Okt11:41:01WIB: crypto46.0.7→50.0.2, pytest9.0.2→9.0.3, pip checkPASS,
dpr-api/dpr-web active. Smoke sebelum dan sesudah65/65 pada14akun; rollback tidak
diperlukan/dijalankan. Backup kode dan venv persis disimpan privat di VM.
PG/OpenBao tidak direstart; tidak provisioning akun, reset database atau rotasi kunci.

SBOM docs/sbom diregenerasi dari main4fdd7aa pada venv laptopPython3.12.10. Tiga
pip-audit requirements: app0/31dependency, benchmark0/22, infra0/16; skipped0.
Npm audit package-lock:0finding. Ada9JSON SBOM/audit; hash/tool/version/scope di
app/evidence/access-control/dependency-upgrade-sbom-20261029.json. Inventory
Windows app+infra+toolkit+audit tools bukan dump seluruh dependency VM; ranged
requirements BOM merekam deklarasi, environment BOM merekam versi terpasang.
VM siap diserahkan ke pentest Delf; hasil upgrade/smoke bukan kesimpulan pentest.
