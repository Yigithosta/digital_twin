import numpy as np
import pytest

from data.simulator import (EQUIPMENT_PROFILES, FEATURES, LiveSimulator, denormalize,
                            gas_status, generate_degradation_run, normalize,
                            operating_limits, resolve_equipment)


@pytest.mark.parametrize("gas, level", [
    (0.4, "NORMAL"), (0.99, "NORMAL"), (1.0, "UYARI"),
    (1.5, "TEHLİKE"), (1.99, "TEHLİKE"), (2.0, "KRİTİK"), (3.2, "KRİTİK"),
])
def test_gas_status_thresholds(gas, level):
    assert gas_status(gas)["seviye"] == level


@pytest.mark.parametrize("eq_id", EQUIPMENT_PROFILES)
def test_normalize_roundtrip(eq_id):
    profile = EQUIPMENT_PROFILES[eq_id]
    mid = [(profile[k][0] + profile[k][1]) / 2 for k in FEATURES]
    assert np.allclose(normalize(mid, eq_id), 0)
    upper = [profile[k][1] for k in FEATURES]
    assert np.allclose(normalize(upper, eq_id), 3)          # aralık = ortalama ± 3 sigma
    assert np.allclose(denormalize(normalize(upper, eq_id), eq_id), upper)


@pytest.mark.parametrize("eq_id", EQUIPMENT_PROFILES)
def test_operating_limits_are_ordered(eq_id):
    limits = operating_limits(eq_id)
    for key in ["temperature", "vibration", "pressure", "current"]:
        lim = limits[key]
        assert lim["lo"] < lim["hi"] < lim["warn"] < lim["crit"]
    assert limits["pressure"]["crit_low"] < limits["pressure"]["warn_low"] < limits["pressure"]["lo"]
    assert limits["gas"]["warn"] < limits["gas"]["crit"] < limits["gas"]["evacuate"]


def test_resolve_equipment():
    assert resolve_equipment("pump_01") == "pump_01"
    assert resolve_equipment("pump_07", "pump") == "pump_01"
    assert resolve_equipment("bilinmeyen", "kompresor") is None


def test_live_simulator_is_reproducible_and_in_range():
    a, b = LiveSimulator(seed=7), LiveSimulator(seed=7)
    for _ in range(200):
        ra = a.step("crusher_01", anomaly_rate=0, gas_rate=0)
        assert ra == b.step("crusher_01", anomaly_rate=0, gas_rate=0)
        for key in FEATURES:
            lo, hi = EQUIPMENT_PROFILES["crusher_01"][key]
            assert lo * 0.9 <= ra[key] <= hi * 1.1
        assert ra["gas"] < 1.0


def test_gas_leak_rises_then_decays():
    sim = LiveSimulator(seed=3)
    sim.step("pump_01", gas_rate=0)
    peak = sim.step("pump_01", force_gas=True, gas_rate=0)["gas"]
    after = [sim.step("pump_01", gas_rate=0)["gas"] for _ in range(12)]
    assert peak >= 1.2
    assert after[0] < peak
    assert after[-1] < 1.0


def test_degradation_run_ends_at_failure():
    run = generate_degradation_run("conveyor_01", steps=80, mode="rulman_asinmasi")
    assert run["rul_hours"].iloc[0] > run["rul_hours"].iloc[-1] == 0
    assert run["vibration"].iloc[-10:].mean() > run["vibration"].iloc[:10].mean() * 2
