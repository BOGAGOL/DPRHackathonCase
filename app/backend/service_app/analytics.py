"""Read only the released A5 marginals; never reconstruct member cohorts."""
from sqlalchemy import BigInteger, Column, MetaData, Table, Text, select

DIMENSIONS = ("jenis_kelamin", "pekerjaan_terakhir", "nama_kppn", "nama_bank", "age_band")
THRESHOLD = 5
ANALYST_SUMMARY = Table("analyst_summary", MetaData(), Column("dimension", Text),
                        Column("value", Text), Column("anggota_count", BigInteger), schema="public")


def summary(db, filters):
    if set(filters) - {"dimension", "value"} or ("value" in filters and not filters.get("dimension")):
        raise ValueError("Member cohort filters are not supported")
    columns = ANALYST_SUMMARY.c
    query = select(columns.dimension, columns.value, columns.anggota_count).where(columns.anggota_count >= THRESHOLD)
    for field, value in filters.items():
        if value is not None:
            query = query.where(columns[field] == value)
    rows = db.execute(query.order_by(columns.dimension, columns.value.nulls_last())).all()
    return {"total": None, "groups": [
        {"dimension": dimension, "value": value, "count": count}
        for dimension, value, count in rows
    ]}
