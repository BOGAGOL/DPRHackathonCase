"""Check the JSON boundary, including small cohorts created by combined filters."""
import pytest
from sqlalchemy import update
from service_app.models import baseline_members
from conftest import login


def test_small_cohort_never_sends_exact_count(lab):
    login(lab, "analyst")
    result = lab.client.get("/analytics/summary")
    assert result.status_code == 200
    assert result.json()["total"] == "<5"
    assert all(g["count"] == "<5" for g in result.json()["groups"])
    assert '"count":3' not in result.text and '"total":3' not in result.text
    assert result.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("count", [1, 4, 5, 6])
def test_threshold_after_kppn_and_profession_filter(lab, count):
    for n in range(4, count + 4):
        lab.add_member(n, {"pekerjaan_terakhir": "Dokter", "nama_kppn": "KPPN Surabaya"})
    login(lab, "analyst")
    result = lab.client.get("/analytics/summary", params={"nama_kppn": "KPPN Surabaya", "pekerjaan_terakhir": "Dokter"})
    assert result.status_code == 200
    expected = "<5" if count < 5 else count
    assert result.json()["total"] == expected
    assert all(g["count"] == expected for g in result.json()["groups"])


def test_subtraction_cannot_recover_lone_small_cell_from_siblings(lab):
    with lab.engine.begin() as db:
        db.execute(update(baseline_members).values(pekerjaan_terakhir="Dokter"))
    for n in range(4, 10):
        lab.add_member(n, {"pekerjaan_terakhir": "Guru"})
    login(lab, "analyst")
    body = lab.client.get("/analytics/summary").json()
    groups = {g["value"]: g["count"] for g in body["groups"] if g["dimension"] == "pekerjaan_terakhir"}
    assert groups == {"Dokter": "<5", "Guru": None}
    assert body["total"] is None


def test_empty_filter_and_sql_payload_do_not_reveal_other_groups(lab):
    login(lab, "analyst")
    result = lab.client.get("/analytics/summary", params={"nama_kppn": "' OR 1=1 --"})
    assert result.status_code == 200 and result.json() == {"total": 0, "groups": []}
    assert lab.client.get("/analytics/summary", params={"no_ktp": "test"}).status_code == 422
    assert lab.client.get("/analytics/summary", params={"age_band": "invalid"}).status_code == 422
    assert lab.client.get("/analytics/summary", params={"nama_kppn": "x" * 51}).status_code == 422


@pytest.mark.parametrize("role", ["operator", "finance_officer", "privileged_officer", "anggota", "auditor"])
def test_filtered_analytics_does_not_bypass_role_policy(lab, role):
    login(lab, role)
    assert lab.client.get("/analytics/summary", params={"nama_kppn": "KPPN Surabaya"}).status_code == 403
