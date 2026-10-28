"""A5/B4: small labels never cross the JSON boundary in either mode."""
import pytest
from pydantic import ValidationError
from sqlalchemy import event, text
from sqlalchemy.dialects import postgresql
from service_app.analytics import summary
from service_app.schemas import Analytics, AnalyticsFilters
from conftest import login


def test_small_cohort_omits_labels_counts_and_total(lab):
    login(lab, "analyst")
    result = lab.client.get("/analytics/summary")
    assert result.status_code == 200
    assert result.json() == {"total": None, "groups": []}
    assert "Peneliti" not in result.text and "KPPN Uji" not in result.text
    assert "<5" not in result.text
    assert result.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 6])
@pytest.mark.parametrize("label", ["Profesi Kelompok Uji", None])
def test_threshold_omits_entire_small_group_including_null(lab, count, label):
    for number in range(4, count + 4):
        lab.add_member(number, {"pekerjaan_terakhir": label})
    login(lab, "analyst")
    result = lab.client.get("/analytics/summary")
    assert result.status_code == 200
    groups = [g for g in result.json()["groups"] if g["dimension"] == "pekerjaan_terakhir"]
    assert groups == ([] if count < 5 else [
        {"dimension": "pekerjaan_terakhir", "value": label, "count": count}
    ])
    if count < 5 and label is not None:
        assert label not in result.text
    assert result.json()["total"] is None
    assert all(g["count"] >= 5 for g in result.json()["groups"])


def test_released_marginal_filters_do_not_create_cohorts(lab):
    for number in range(4, 10):
        lab.add_member(number, {"pekerjaan_terakhir": "Guru Uji"})
    login(lab, "analyst")
    result = lab.client.get("/analytics/summary", params={"dimension": "pekerjaan_terakhir", "value": "Guru Uji"})
    assert result.status_code == 200
    assert result.json() == {"total": None, "groups": [
        {"dimension": "pekerjaan_terakhir", "value": "Guru Uji", "count": 6}
    ]}
    hidden = lab.client.get("/analytics/summary", params={"dimension": "pekerjaan_terakhir", "value": "Peneliti"})
    assert hidden.json() == {"total": None, "groups": []}


@pytest.mark.parametrize("filters", [
    {"nama_kppn": "KPPN Kelompok Kecil"},
    {"nama_kppn": "KPPN Kelompok Kecil", "pekerjaan_terakhir": "Dokter"},
    {"age_band": "40-49"}, {"jenis_kelamin": "P"}, {"nama_bank": "Bank Uji"},
    {"dimension": "age_band", "nama_kppn": "KPPN Uji"},
])
def test_member_cohort_filters_are_explicitly_rejected(lab, filters):
    login(lab, "analyst")
    result = lab.client.get("/analytics/summary", params=filters)
    assert result.status_code == 422
    assert "Filter cohort anggota tidak didukung" in result.json()["detail"]
    assert "KPPN Kelompok Kecil" not in result.text


@pytest.mark.parametrize("filters", [
    {"value": "Guru"}, {"dimension": "no_ktp"}, {"dimension": "age_band", "value": "x" * 51},
    {"dimension": "age_band", "value": ""},
])
def test_invalid_released_filters_are_rejected(lab, filters):
    login(lab, "analyst")
    assert lab.client.get("/analytics/summary", params=filters).status_code == 422


def test_query_uses_only_summary_with_bound_values_and_no_fallback(lab):
    for number in range(4, 9):
        lab.add_member(number)
    login(lab, "analyst")
    statements = []

    def record_query(connection, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))

    event.listen(lab.app.state.engine, "before_cursor_execute", record_query)
    try:
        payload = "' OR 1=1 --"
        result = lab.client.get("/analytics/summary", params={"dimension": "nama_kppn", "value": payload})
        assert result.status_code == 200 and result.json() == {"total": None, "groups": []}
        queries = [(sql, params) for sql, params in statements if "analyst_summary" in sql]
        assert len(queries) == 1
        sql, params = queries[0]
        assert payload not in sql and payload in params
        assert "analyst_view" not in sql and "count(" not in sql.lower()
        with lab.engine.begin() as db:
            db.execute(text("DROP VIEW analyst_summary"))
        failed = lab.client.get("/analytics/summary")
        assert failed.status_code == 503
        assert failed.json() == {"detail": "Layanan data tidak tersedia"}
        assert "analyst_view" not in failed.text and "Peneliti" not in failed.text
        assert not any("FROM analyst_view" in sql for sql, _ in statements)
    finally:
        event.remove(lab.app.state.engine, "before_cursor_execute", record_query)


def test_app_defense_also_drops_small_labels_from_invalid_view(lab):
    with lab.engine.begin() as db:
        db.execute(text("DROP VIEW analyst_summary"))
        db.execute(text("CREATE VIEW analyst_summary AS SELECT 'nama_kppn' AS dimension, 'Label Kecil Rahasia Uji' AS value, 4 AS anggota_count"))
    login(lab, "analyst")
    result = lab.client.get("/analytics/summary")
    assert result.status_code == 200
    assert result.json() == {"total": None, "groups": []}
    assert "Label Kecil Rahasia Uji" not in result.text


def test_postgresql_projection_is_public_and_internal_cohort_calls_fail():
    class Capture:
        def execute(self, query):
            self.query = query
            return self

        def all(self):
            return [("nama_bank", "Bank Uji", 5)]

    db = Capture()
    assert summary(db, {"dimension": "nama_bank"}) == {
        "total": None, "groups": [{"dimension": "nama_bank", "value": "Bank Uji", "count": 5}]
    }
    compiled = db.query.compile(dialect=postgresql.dialect())
    assert "FROM public.analyst_summary" in str(compiled)
    assert "NULLS LAST" in str(compiled)
    assert compiled.params["dimension_1"] == "nama_bank"
    with pytest.raises(ValueError):
        summary(db, {"nama_kppn": "KPPN Uji"})
    with pytest.raises(ValueError):
        summary(db, {"value": "KPPN Uji"})


def test_dto_rejects_small_counts_raw_totals_and_unknown_dimensions():
    for count in [1, 4, "<5", None]:
        with pytest.raises(ValidationError):
            Analytics(total=None, groups=[{"dimension": "age_band", "value": "40-49", "count": count}])
    with pytest.raises(ValidationError):
        Analytics(total=734, groups=[])
    with pytest.raises(ValidationError):
        Analytics(total=None, groups=[{"dimension": "no_ktp", "value": "Uji", "count": 5}])
    assert AnalyticsFilters(dimension="nama_kppn", value="KPPN Uji").value == "KPPN Uji"
    with pytest.raises(ValidationError):
        AnalyticsFilters(value="KPPN Uji")


@pytest.mark.parametrize("role", ["operator", "finance_officer", "privileged_officer", "anggota", "auditor"])
def test_released_filters_do_not_bypass_role_policy(lab, role):
    login(lab, role)
    assert lab.client.get("/analytics/summary", params={"dimension": "nama_kppn"}).status_code == 403
