"""Altyapı servisleri (veritabanı, MQTT, Qdrant) gerektirmeyen uç nokta testleri."""

import pytest
from fastapi.testclient import TestClient

import main

# `with` kullanılmadığı için uygulamanın açılış adımları (bağlantılar) çalışmaz.
client = TestClient(main.app)


def test_info():
    body = client.get("/api").json()
    assert body["versiyon"] == main.VERSION


def test_panel_is_served_at_root():
    res = client.get("/")
    assert res.status_code == 200
    assert "Maden Dijital İkiz" in res.text


def test_equipment_catalog():
    catalog = client.get("/equipment").json()
    assert {e["id"] for e in catalog} == {"conveyor_01", "pump_01", "crusher_01"}
    for eq in catalog:
        assert eq["limits"]["temperature"]["warn"] < eq["limits"]["temperature"]["crit"]
        assert eq["units"]["speed"] in {"m/s", "rpm"}


def test_timeseries_rejects_unknown_metric():
    res = client.get("/dashboard/timeseries/pump_01/password")
    assert res.status_code == 400


@pytest.mark.parametrize("path", ["/predict/yok_01", "/predict/rul/yok_01"])
def test_predict_unknown_equipment(path):
    assert client.get(path).status_code == 404


def test_reading_validation():
    bad = {"equipment_id": "pump_01", "temperature": 40, "vibration": -1,
           "pressure": 6, "current": 28, "speed": 1470}
    assert client.post("/sensors/reading", json=bad).status_code == 422
    unknown = {**bad, "equipment_id": "yok_01", "vibration": 1}
    assert client.post("/sensors/reading", json=unknown).status_code == 404


def test_rag_question_validation():
    assert client.post("/rag/sor", json={"soru": ""}).status_code == 422
