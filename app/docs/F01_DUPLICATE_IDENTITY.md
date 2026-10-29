# F-01: penegakan identitas unik

Aturan bisnis dari instruksi Zhafif pada 29 Oktober 2026: satu `no_ktp` non-NULL
hanya boleh ada pada satu record anggota. Dataset sintetis 14 digit tetap valid;
tidak dipaksa menjadi 16 digit dan nol awal tidak dibuang. Nilai NULL tetap NULL.

`sql/protected/04_identity_unique.sql` membuat UNIQUE index global
`uq_anggota_protected_no_ktp_bidx` pada `anggota_protected(no_ktp_bidx)`.
Indeks menggunakan HMAC toolkit yang sudah ada, tanpa plaintext tambahan atau
perubahan format crypto. Pemeriksaan dan pemasangan ada dalam satu transaksi
dengan lock tabel; duplikat existing menyebabkan rollback, bukan cleanup otomatis.
Indeks existing bernama sama tetapi nonunique/partial/invalid ditolak.

Database menjadi pengaman atomik terhadap concurrent insert, termasuk ketika
record existing tidak terlihat lewat RLS. Tidak mengandalkan pre-check SELECT
yang dapat melewatkan record tersembunyi atau kalah dalam race condition.

API mengembalikan `409` dengan body:

```json
{"detail":"Data tidak dapat dibuat karena konflik identitas"}
```

Tidak ada ID existing, plaintext, blind index atau detail exception di respons.
Transaksi dibatalkan sebelum audit `insert/denied` ditulis. Error integrity lain
tetap menggunakan error database generik. Respons konflik memberi sinyal bahwa
identitas tidak tersedia, sebagaimana perilaku unique field; tidak membuka record.

POST menerima digit dengan separator spasi, titik dan tanda hubung, lalu memvalidasi
hasil 14/16 digit sebelum menyimpan. Huruf dan digit Unicode yang menyerupai ASCII
ditolak. Search tetap mengikuti normalisasi kontrak yang sama. Email dan `pengguna`
tidak ikut dibuat unique karena kontrak tidak menetapkan invariant tersebut.

Plain API memakai cek dalam transaksi setelah advisory lock PostgreSQL per KTP,
sehingga API request yang bersamaan juga menghasilkan satu sukses. Schema baseline
milik C tidak diubah. Writer SQL langsung di lingkungan plaintext terkontrol tidak
tercakup invariant aplikasi tersebut; UNIQUE persistensi global berlaku protected.

## Pengujian ulang lokal

```powershell
app/.venv/Scripts/python.exe -m pytest -c app/pytest.ini app/tests/test_duplicate_identity.py app/tests/test_f01_cli.py app/tests/test_golden_reset.py -q
```

Pengujian native `app/tests/test_f01_postgres.py` memerlukan environment
`DPR_F01_TEST_DATABASE_URL` ke cluster PostgreSQL18 disposable dengan database
admin `dpr_f01_tests` dan custom setting `dpr.test_cluster=f01`. Hanya loopback
dan cluster bertanda yang diterima; setiap test memakai database UUID baru dan
menghapus hanya database ciptaannya. Crypto test double dipakai khusus fixture.

Pada pengerjaan ini suite lengkap dengan native PG menghasilkan 482 PASS/3 SKIP.
Dua request HTTP paralel benar-benar mencapai INSERT bersamaan pada protected:
satu 201, satu 409, search sesudahnya satu hasil. Tes juga mencakup format KTP,
scope RLS, audit/DTO aman, penolakan migrasi saat data duplikat, indeks salah,
idempotence, NULL, dan pengaman reset golden.

## Penerapan dan pemulihan

1. Hentikan pengujian mutasi Delf sementara. Catat metadata jumlah anggota,
   duplicate group, dan keberadaan ID735/737; jangan ekspor nilai KTP.
2. Backup source yang akan ditimpa secara privat. Jalankan reset resmi:
   `bash scripts/deploy/reset_to_golden.sh protected_734`. Audit lama diekspor
   oleh tooling reset; data kembali ke 734 anggota dengan akun demo/pt dari golden.
3. Hentikan hanya dua service DPR selama pemasangan. Jalankan CLI dengan
   environment operator privat (`handoff/app.env` dan `handoff/setup.env`):

   ```bash
   app/.venv/bin/python app/scripts/f01_identity.py apply --evidence app/evidence/access-control/f01-migration.json
   ```

4. Deploy kode dari commit yang diuji dan restart `dpr-api.service` serta
   `dpr-web.service`. Jalankan smoke 65 pemeriksaan/14 akun.
5. Uji duplicate POST terhadap fixture existing melalui akun `pt.privileged.a`:
   nilai canonical dan berformat sama-sama409, search1, jumlah anggota tetap734.
   Jangan membuat identitas baru di VM untuk mengulang race test lokal.
6. Serahkan retest ke Delf; `pentest_tool.sh disable` dijalankan **paling akhir**.

Versi baru `golden_reset.py` menerapkan ulang SQL04 sebelum memulai service pada
setiap reset. Golden template tetap utuh. Jika DDL gagal, aplikasi tetap berhenti;
jangan menghapus UNIQUE index atau membuka jalur insert lama sebagai fallback.
Restore backup lama oleh Modul A juga perlu SQL04 sebelum write API dibuka kembali.
PostgreSQL/OpenBao tidak perlu restart, tidak ada rotasi kunci atau re-enkripsi.
Pengukuran benchmark historis tidak diubah seolah sudah memakai patch ini.

Evidence akhir: `app/evidence/access-control/fix-F01-duplicate-identity.json`;
detail lokal: `app/evidence/access-control/f01-local-tests.json`.

## Hasil VM terkonfirmasi

Source commit `5e643b1` dipasang lewat arsip terverifikasi, tanpa Git checkout.
Selesai 29 Oktober 2026 pukul 14:08:54 WIB. Sebelum perbaikan ada 737 anggota,
satu kelompok KTP duplikat dan ID735/737 masih ada. Sesudahnya ada 734 anggota,
tidak ada kelompok duplikat/ID735/737, dan indeks unique terverifikasi valid.

Reset database pertama berhasil, tetapi smoke awal hanya 53/65. Diagnosis
baca-saja menunjukkan OpenBao sehat/unsealed, scope pt benar, dan token runtime
ditolak403. Dengan izin tambahan eksplisit Zhafif, token svc-app saja diterbitkan
ulang selama empat jam melalui CLI A dan runtime handoff diperbarui. Tidak ada
rotasi kunci/perubahan policy/restart OpenBao atau PostgreSQL. Resume memakai
database yang sudah dipulihkan, **tanpa reset kedua**.

Smoke akhir65/65 pada14akun; dua service aktif. Uji HTTP di VM melalui pt fixture
existing: canonical409, berformat409, search1, jumlah anggota tetap734. Tidak ada
anggota baru yang disisipkan untuk uji paralel di VM; race sudah diuji di PG18
disposable lokal. Akun pt tetap aktif untuk retest independen Delf.

Laporan percobaan awal tetap disimpan sebagai `f01-initial-attempt.json`, bukan
dihapus agar hasil tampak selalu lulus. `f01-deployment-verification.json` mencatat
provenance rilis, pemulihan token yang diizinkan, dan hasil final. F-01 siap retest;
status Closed tetap ditentukan pentester setelah retest. PR17 menunggu review tim
sebelum merge main; VM menjalankan fix commit tersebut.
