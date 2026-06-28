import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Dict

# Ekipman başına normal çalışma aralıkları
EQUIPMENT_PROFILES = {
    "conveyor_01": {
        "type": "conveyor",
        "temperature": (45, 65),   # °C
        "vibration": (1.5, 4.5),   # mm/s
        "pressure": (2.0, 4.0),    # bar
        "current": (18, 28),       # A
        "speed": (1.2, 1.8),       # m/s
        "gas": (0.1, 0.6),         # % CH4 (metan) — ortam fonu
    },
    "pump_01": {
        "type": "pump",
        "temperature": (35, 55),
        "vibration": (0.5, 2.5),
        "pressure": (5.0, 8.0),
        "current": (22, 35),
        "speed": (1450, 1490),     # RPM
        "gas": (0.1, 0.6),
    },
    "crusher_01": {
        "type": "crusher",
        "temperature": (50, 75),
        "vibration": (3.0, 6.5),
        "pressure": (3.0, 6.0),
        "current": (30, 45),
        "speed": (280, 320),       # RPM
        "gas": (0.1, 0.7),
    },
}

# ── Metan (CH4) Güvenlik Eşikleri — İSG ──────────────────────────────────────
# Madencilik regülasyonlarına göre mutlak metan sınırları (% hacim CH4).
# Metan, ML anomali değil; sabit yasal eşiklerle izlenen bir güvenlik parametresidir.
METHANE_LIMITS = {
    "uyari":   1.0,   # %1.0 üzeri: uyarı, havalandırma kontrol
    "tehlike": 1.5,   # %1.5 üzeri: elektrikli ekipmanı durdur
    "kritik":  2.0,   # %2.0 üzeri: TAHLİYE (patlama aralığı %5-15)
}


def gas_status(gas_pct: float) -> dict:
    """Metan seviyesini İSG durumuna sınıflandırır."""
    if gas_pct >= METHANE_LIMITS["kritik"]:
        return {"seviye": "KRİTİK", "renk": "kirmizi",
                "mesaj": f"TAHLİYE — Metan %{gas_pct:.2f} (patlama riski). Tüm personel tahliye edilmeli."}
    if gas_pct >= METHANE_LIMITS["tehlike"]:
        return {"seviye": "TEHLİKE", "renk": "turuncu",
                "mesaj": f"Metan %{gas_pct:.2f} — Elektrikli ekipmanı durdurun, havalandırmayı artırın."}
    if gas_pct >= METHANE_LIMITS["uyari"]:
        return {"seviye": "UYARI", "renk": "sari",
                "mesaj": f"Metan %{gas_pct:.2f} — Eşik aşıldı, havalandırma kontrol edilmeli."}
    return {"seviye": "NORMAL", "renk": "yesil",
            "mesaj": f"Metan %{gas_pct:.2f} — Güvenli aralık."}


def _normal_reading(profile: dict) -> dict:
    reading = {}
    for key in ["temperature", "vibration", "pressure", "current", "speed"]:
        lo, hi = profile[key]
        reading[key] = round(np.random.normal((lo + hi) / 2, (hi - lo) / 6), 3)
        reading[key] = float(np.clip(reading[key], lo * 0.9, hi * 1.1))
    # Metan: çoğunlukla düşük fon seviyesi (sağa çarpık)
    lo, hi = profile.get("gas", (0.1, 0.6))
    gas = np.random.normal((lo + hi) / 2, (hi - lo) / 4)
    reading["gas"] = float(np.clip(round(gas, 3), 0.0, hi * 1.2))
    return reading


def _anomaly_reading(profile: dict) -> dict:
    reading = _normal_reading(profile)
    fault = np.random.choice(["overheat", "vibration_spike", "overcurrent", "pressure_surge"])
    if fault == "overheat":
        reading["temperature"] *= np.random.uniform(1.3, 1.6)
    elif fault == "vibration_spike":
        reading["vibration"] *= np.random.uniform(2.0, 3.5)
    elif fault == "overcurrent":
        reading["current"] *= np.random.uniform(1.4, 1.8)
    elif fault == "pressure_surge":
        reading["pressure"] *= np.random.uniform(1.5, 2.0)
    return reading


# ── RUL (Kalan Faydalı Ömür) — Degradasyon / Arızaya Kadar veri ──────────────

# Kritik eşikler: normal üst sınırın anomali çarpanı kadar üstü.
# (_anomaly_reading'deki çarpanlarla tutarlı; sensör bu seviyeye ulaşınca arıza.)
CRITICAL_MULTIPLIERS = {
    "temperature": 1.45,
    "vibration":   2.8,
    "current":     1.6,
    "pressure":    1.7,
}

# Arıza modlarının hangi sensörleri nasıl etkilediği
DEGRADATION_MODES = {
    "rulman_asinmasi":  {"primary": "vibration",   "secondary": "temperature", "sec_factor": 0.45},
    "asiri_isinma":     {"primary": "temperature", "secondary": "current",     "sec_factor": 0.40},
    "asiri_akim":       {"primary": "current",     "secondary": "temperature", "sec_factor": 0.35},
    "basinc_kaybi":     {"primary": "pressure",    "secondary": None,          "sec_factor": 0.0},
}

# Etiketleme için zaman ölçeği: her adım 30 dakika (gerçekçi bakım ufku)
STEP_HOURS = 0.5


def critical_thresholds(equipment_id: str) -> dict:
    """Ekipmanın her sensörü için arıza (kritik) eşiği."""
    profile = EQUIPMENT_PROFILES[equipment_id]
    th = {}
    for key, mult in CRITICAL_MULTIPLIERS.items():
        lo, hi = profile[key]
        th[key] = round(hi * mult, 2)
    return th


def generate_degradation_run(equipment_id: str, steps: int = None,
                             mode: str = None) -> pd.DataFrame:
    """
    Bir ekipman için 'sağlıklı → arıza' (run-to-failure) zaman serisi üretir.
    İlgili sensör, normal seviyeden kritik eşiğe doğru kademeli olarak (üstel
    hızlanan + gürültülü) kayar. Her satır 'health' (0-1) ve 'rul_hours' içerir.
    """
    profile = EQUIPMENT_PROFILES[equipment_id]
    if steps is None:
        steps = int(np.random.randint(80, 200))
    if mode is None:
        mode = np.random.choice(list(DEGRADATION_MODES.keys()))
    spec = DEGRADATION_MODES[mode]
    crit = critical_thresholds(equipment_id)

    rows = []
    for i in range(steps):
        progress = i / max(1, steps - 1)          # 0 → 1
        # üstel hızlanma: arıza sona yaklaştıkça degradasyon hızlanır
        sev = progress ** 1.7
        reading = _normal_reading(profile)

        prim = spec["primary"]
        if prim == "pressure":
            # basınç kaybı: aşağı yönlü degradasyon
            lo = profile["pressure"][0]
            target_low = lo * 0.45
            reading["pressure"] = float(lo - (lo - target_low) * sev
                                        + np.random.normal(0, 0.08))
        else:
            hi = profile[prim][1]
            reading[prim] = float(hi + (crit[prim] - hi) * sev
                                  + np.random.normal(0, (crit[prim] - hi) * 0.04))

        sec = spec["secondary"]
        if sec:
            hi_s = profile[sec][1]
            reading[sec] = float(reading[sec]
                                 + (crit[sec] - hi_s) * sev * spec["sec_factor"])

        health = max(0.0, 1.0 - progress)
        rul = (steps - 1 - i) * STEP_HOURS

        reading["equipment_id"]   = equipment_id
        reading["equipment_type"] = profile["type"]
        reading["mode"]           = mode
        reading["health"]         = round(health, 4)
        reading["rul_hours"]      = round(rul, 3)
        rows.append(reading)

    return pd.DataFrame(rows)


def generate_healthy_run(equipment_id: str, steps: int = None) -> pd.DataFrame:
    """
    Sağlıklı (sansürlü) çalışma serisi: makine gözlem boyunca arızalanmaz.
    Tüm pencereler maksimum RUL ile etiketlenir → model 'durağan normal = sağlıklı'
    ilişkisini öğrenir. (Standart RUL veri setlerindeki right-censored örnekler.)
    """
    profile = EQUIPMENT_PROFILES[equipment_id]
    if steps is None:
        steps = int(np.random.randint(40, 80))
    rows = []
    for _ in range(steps):
        reading = _normal_reading(profile)
        reading["equipment_id"]   = equipment_id
        reading["equipment_type"] = profile["type"]
        reading["mode"]           = "saglikli"
        reading["health"]         = 1.0
        reading["rul_hours"]      = float(STEP_HOURS * 200)  # tavan (RUL_MAX ile aynı)
        rows.append(reading)
    return pd.DataFrame(rows)


def generate_rul_dataset(runs_per_equipment: int = 40) -> pd.DataFrame:
    """
    RUL eğitim seti: her ekipman için degradasyon (arızaya kadar) + sağlıklı run'lar.
    Her run benzersiz 'run_id' taşır (eğitimde pencereler run sınırını aşmasın).
    """
    frames = []
    rid = 0
    for eq_id in EQUIPMENT_PROFILES:
        for _ in range(runs_per_equipment):
            df = generate_degradation_run(eq_id)
            df["run_id"] = rid; rid += 1
            frames.append(df)
        # degradasyonun yarısı kadar sağlıklı run (dengeli sınıf)
        for _ in range(runs_per_equipment // 2):
            df = generate_healthy_run(eq_id)
            df["run_id"] = rid; rid += 1
            frames.append(df)
    return pd.concat(frames, ignore_index=True)


def generate_reading(equipment_id: str, force_anomaly: bool = False,
                     force_gas: bool = False) -> Dict:
    profile = EQUIPMENT_PROFILES.get(equipment_id, list(EQUIPMENT_PROFILES.values())[0])
    is_anomaly = force_anomaly or (np.random.random() < 0.05)
    reading = _anomaly_reading(profile) if is_anomaly else _normal_reading(profile)

    # Metan kaçağı: mekanik anomaliden bağımsız bir İSG olayı.
    # force_gas ile demoda tetiklenir; aksi halde düşük olasılıkla ortaya çıkar.
    if force_gas or (np.random.random() < 0.02):
        reading["gas"] = float(round(np.random.uniform(1.2, 2.6), 3))

    reading["equipment_id"] = equipment_id
    reading["equipment_type"] = profile["type"]
    return reading


def generate_training_data(n_samples: int = 2000) -> pd.DataFrame:
    rows = []
    equipment_ids = list(EQUIPMENT_PROFILES.keys())
    for _ in range(n_samples):
        eq_id = np.random.choice(equipment_ids)
        profile = EQUIPMENT_PROFILES[eq_id]
        is_anomaly = np.random.random() < 0.05
        reading = _anomaly_reading(profile) if is_anomaly else _normal_reading(profile)
        reading["equipment_id"] = eq_id
        reading["is_anomaly"] = is_anomaly
        rows.append(reading)
    return pd.DataFrame(rows)


def generate_historical(hours: int = 24, interval_seconds: int = 30) -> pd.DataFrame:
    rows = []
    now = datetime.now(timezone.utc)
    equipment_ids = list(EQUIPMENT_PROFILES.keys())
    t = now - timedelta(hours=hours)
    while t <= now:
        for eq_id in equipment_ids:
            reading = generate_reading(eq_id)
            reading["time"] = t
            rows.append(reading)
        t += timedelta(seconds=interval_seconds)
    return pd.DataFrame(rows)
