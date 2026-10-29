# 9. Referensi, sumber implementasi dan atribusi

Nomor R berikut dapat dipakai untuk daftar pustaka PDF. Sumber kode/evidence
membuktikan implementasi, sumber primer menjelaskan mekanisme, dan dokumen panitia
menentukan persyaratan. Ketiganya tidak saling menggantikan.

| ID | Sumber | Pemakaian dan batas |
|---|---|---|
| R01 | Dewan Juri Hackathon DPR RI. 2026. *Database Bocor: Seberapa Jauh Data Pribadi Tetap Terlindungi?* signed-2026920-SOAL FINAL HACKATHON DPR RI 2026.pdf,4halaman | T1–T6 dan luaran; salinan diberikan pengguna, diperiksa ulang |
| R02 | Panitia. *DPR RI: Detail Hackaton Syarat Peserta, Proses Penjurian*,8halaman | Wajib teknis/h.4–6,15luaran/h.7,lisensi/jadwal; ejaan judul mengikuti berkas |
| R03 | Onno W. Purbo.2026. *Data Leak-Proof: Teknik Proteksi Data di PostgreSQL agar Kebocoran Tidak Berarti Apa-Apa* | Rujukan envelope/risiko/profile/role/backup; bukan seluruh kode hasilkarya tim |
| R04 | Onno W. Purbo. *Overview Serangan ke Data dan Database* | Ancaman/inferensi/jalurserangan; metadataedisi/halaman harusdicocokkanbukufinal |
| R05 | Republik Indonesia. [UU No.27 Tahun2022 tentang Pelindungan Data Pribadi](https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022) | Istilah/kelasdata; bukan sertifikatkepatuhan prototipe |
| R06 | PostgreSQL Global Development Group. [PostgreSQL 18: Row Security Policies](https://www.postgresql.org/docs/18/ddl-rowsecurity.html) | PeranRLS/defaultdeny/ownerprivilege; konfigurasiaktual dibuktikanSQL/test |
| R07 | PostgreSQL. [libpq SSL Support](https://www.postgresql.org/docs/18/libpq-ssl.html) | verify-full membanguntrustCA dan identitashost |
| R08 | PostgreSQL. [pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html),[pg_restore](https://www.postgresql.org/docs/18/app-pgrestore.html) | Dumpcustom/restore; enkripsiframing ditambahkanproyek |
| R09 | OpenBao. [Transit API](https://openbao.org/api-docs/secret/transit/) | Wrap/decrypt/HMAC/batch/rewrap; dokumentasigenerik dapatberubah |
| R10 | OpenBao.[Source encrypt v2.5.5](https://github.com/openbao/openbao/blob/v2.5.5/builtin/logical/transit/path_encrypt.go),[decrypt](https://github.com/openbao/openbao/blob/v2.5.5/builtin/logical/transit/path_decrypt.go),[HMAC](https://github.com/openbao/openbao/blob/v2.5.5/builtin/logical/transit/path_hmac.go) | Versiyangdipin; associated_data/context, formatdanversiHMAC |
| R11 | cryptography.[Authenticated encryption46.0.5](https://cryptography.io/en/46.0.5/hazmat/primitives/aead/) | AESGCM/AAD/nonce/InvalidTag; dependencybenchmark aktual46.0.7dicatat terpisah |
| R12 | CycloneDX.[Specification1.6 JSONschema](https://cyclonedx.org/schema/bom-1.6.schema.json) | FormatSBOM; BOMbukan CVEscan atau inventarisOSlengkap |
| R13 | CreativeCommons.[CCBY-NC4.0](https://creativecommons.org/licenses/by-nc/4.0/) | Dokumentasiorisinal saja; kodemengikutiMIT |
| R14 | TimBOGAGOL.Kode/evidence snapshot4877fc7/main 96c9edb | Kontrak, profile, SQL, tool/app/runner dan file hasil; path/hash dalammanifest |

Sumber primer R05/R06/R07/R09/R11/R13 diperiksa melalui akses web pada sesi
penyusunan29Okt2026WIB; bukti associated_data menggunakan catatan probe/tag2.5.5
yang telah ada. Link R08/R10/R12 adalah rujukan lanjutan, bukan klaim semua halaman
tersebut dijalankan/dibaca ulang sebagai pengujian proyek pada sesi ini.

Metodologi groundtruth repo menyebut beberapa nomor halaman buku. Paket ini
tidak memverifikasi ulang buku lengkap, sehingga **jangan menyalin nomor halaman
tersebut sebagai kutipan yang sudah diperiksa**. Gunakan bab/judul sementara,
cocokkan edisi/halaman secara manual sebelum PDFfinal.

## Adaptasi rujukan Onno yang harus dijelaskan

Rujukan buku menyediakan ide awal. Tim mengadaptasi envelope per record/domain,
AADlokal, token policy TTL, TLSverify dan backupstreaming. Kekurangan rujukan yang
ditangani: context bukan AAD, tokenstatis, plaintextdumpsementara, dan quickstart
TLSoff. Jangan menyatakan semua mekanismekripto ditemukan tim; kontribusi pada
assessmentprofile, residual/inferensi, domainsplit dan evidence yang dapatditelusuri.

## Lisensi dan AI

Kode sumber MIT; dokumentasiorisinal CCBY-NC4.0; datasetpanitia khususkompetisi,
tidakboleh dipublikasikan. Komponen pihak ketiga/buku/logo mengikuti pemiliknya.
Repo tetapPRIVATE karena riwayatdapatmemuatdataset meskipun tidakdimasukkanpaket.
Jangan upload folderkerja/.git/privatekeys/knownvalues. Narasi penggunaan AI harus
jujur: bantuan kode/test/audit/dokumen; reviewer/approval belumdicatat tidak boleh
diciptakan. SBOM padaappendix menjelaskan scoperange/pin/transitif dan lisensi
lockfile yangtersedia, tidak mengarang lisensipaket yang tidakdinyatakan.
