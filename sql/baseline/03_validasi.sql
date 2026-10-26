SELECT count(*) AS total_baris FROM anggota;                 -- harus 734
SELECT count(DISTINCT no_ktp) AS ktp_unik FROM anggota;       -- harus 734
SELECT min(length(no_ktp)), max(length(no_ktp)) FROM anggota; -- 14 dan 14 (nol depan utuh)
SELECT count(*) FILTER (WHERE status_kawin='K') AS kawin,
       count(tanggal_pernikahan) AS ada_tgl_nikah FROM anggota; -- 367 dan 367
