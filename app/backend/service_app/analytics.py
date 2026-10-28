"""Bounded aggregate queries and small-cell suppression before DTO serialization."""
from sqlalchemy import func, select
from .models import analyst_view

DIMENSIONS = ("jenis_kelamin", "pekerjaan_terakhir", "nama_kppn", "nama_bank", "age_band")
THRESHOLD = 5


def summary(db, filters):
    predicates = [analyst_view.c[field] == value for field, value in filters.items() if value is not None]
    total = db.scalar(select(func.count()).select_from(analyst_view).where(*predicates))
    groups = []
    any_small = False
    for field in DIMENSIONS:
        column = analyst_view.c[field]
        rows = db.execute(select(column, func.count()).where(*predicates).group_by(column).order_by(column).limit(101)).all()
        small = [i for i, (_, count) in enumerate(rows) if 0 < count < THRESHOLD]
        any_small |= bool(small)
        # When exactly one cell is small, suppress one additional cell so the
        # small count cannot be recovered by subtracting its siblings from a total.
        secondary = next((i for i, (_, n) in enumerate(rows) if n >= THRESHOLD), None) if len(small) == 1 else None
        for i, (value, count) in enumerate(rows[:100]):
            released = "<5" if i in small else None if i == secondary else count
            groups.append({"dimension": field, "value": value, "count": released})
    released_total = "<5" if 0 < total < THRESHOLD else None if any_small else total
    return {"total": released_total, "groups": groups}
