import numpy as np
import pytest

from app.services.anomaly_detector import detect
from data.simulator import EQUIPMENT_PROFILES, _anomaly_reading, _normal_reading


def _reading(eq_id, anomalous=False):
    profile = EQUIPMENT_PROFILES[eq_id]
    r = (_anomaly_reading if anomalous else _normal_reading)(profile)
    return {**r, "equipment_id": eq_id, "equipment_type": profile["type"]}


@pytest.fixture(autouse=True)
def _seed():
    np.random.seed(1234)


@pytest.mark.parametrize("eq_id", EQUIPMENT_PROFILES)
def test_normal_readings_rarely_flagged(eq_id):
    results = [detect(_reading(eq_id)) for _ in range(400)]
    assert sum(r["is_anomaly"] for r in results) <= 8          # yanlış alarm < %2
    assert all(r["description"] is None for r in results if not r["is_anomaly"])


@pytest.mark.parametrize("eq_id", EQUIPMENT_PROFILES)
def test_fault_readings_mostly_flagged(eq_id):
    results = [detect(_reading(eq_id, anomalous=True)) for _ in range(400)]
    assert sum(r["is_anomaly"] for r in results) >= 360         # duyarlılık > %90


def test_score_is_calibrated_around_threshold():
    for eq_id in EQUIPMENT_PROFILES:
        for anomalous in (False, True):
            for _ in range(100):
                r = detect(_reading(eq_id, anomalous))
                assert 0.0 <= r["anomaly_score"] <= 1.0
                assert r["is_anomaly"] == (r["anomaly_score"] > 0.5)


def test_description_names_the_deviating_sensor():
    reading = {"equipment_id": "pump_01", "equipment_type": "pump", "temperature": 45,
               "vibration": 7.5, "pressure": 6.5, "current": 28, "speed": 1470}
    result = detect(reading)
    assert result["is_anomaly"]
    assert "titreşim" in result["description"]
    assert "sıcaklık" not in result["description"]


def test_unknown_equipment_is_rejected():
    with pytest.raises(ValueError):
        detect({"equipment_id": "x", "equipment_type": "y", "temperature": 1,
                "vibration": 1, "pressure": 1, "current": 1, "speed": 1})
