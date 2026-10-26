-- Schema baseline (plaintext v1) untuk dump anggota_dummy.sql
-- Sengaja meniru kondisi awal soal: data sensitif masih plaintext.
DROP TABLE IF EXISTS anggota;
CREATE TABLE anggota (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nama                VARCHAR(100) NOT NULL,
    nama_lengkap        VARCHAR(100),
    nama_tanpa_gelar    VARCHAR(100),
    jenis_kelamin       CHAR(1) CHECK (jenis_kelamin IN ('L','P')),
    tempat_lahir        VARCHAR(50),
    tanggal_lahir       DATE,
    tanggal_pernikahan  DATE,
    no_ktp              VARCHAR(20),
    pekerjaan_terakhir  VARCHAR(50),
    alamat_jakarta      VARCHAR(255),
    telpon_jakarta      VARCHAR(20),
    alamat_daerah       VARCHAR(255),
    telpon_daerah       VARCHAR(20),
    handphone           VARCHAR(20),
    email               VARCHAR(150),
    ruangan             VARCHAR(20),
    status_kawin        VARCHAR(2),
    jumlah_anak         SMALLINT,
    jumlah_tanggungan   SMALLINT,
    jumlah_jiwa         SMALLINT,
    rekening            VARCHAR(30),
    nama_rekening       VARCHAR(100),
    npwp                VARCHAR(20),
    nama_kppn           VARCHAR(50),
    nip_kppn            VARCHAR(20),
    nama_bank           VARCHAR(50),
    kode_bank           VARCHAR(5),
    pengguna            VARCHAR(100),
    agama               VARCHAR(20)
);
-- Nomor identitas disimpan sebagai teks (bukan angka) supaya nol di depan tidak hilang.
CREATE INDEX idx_anggota_no_ktp   ON anggota (no_ktp);
CREATE INDEX idx_anggota_email    ON anggota (email);
CREATE INDEX idx_anggota_hp       ON anggota (handphone);
CREATE INDEX idx_anggota_pengguna ON anggota (pengguna);
