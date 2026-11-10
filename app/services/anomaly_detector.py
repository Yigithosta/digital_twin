"""
Isolation Forest tabanlı anomali tespiti.

Model, ekipman profiline göre normalize edilmiş (z-skor) özelliklerle çalışır.
Sahadaki arızalar çoğunlukla tek bir sensörde başlar; ağaçların bunu kolay
ayırabilmesi için z-skorlara iki özet özellik eklenir: en büyük mutlak sapma
ve sapma vektörünün normu.

Eğitim ml/train.py içindedir. Kayıtlı model yoksa ilk çağrıda aynı yöntemle
eğitilir.
"""

import os
import pickle
from typing import Dict

import numpy as np

from data.simulator import (EQUIPMENT_PROFILES, FEATURES, critical_thresholds,
                            normalize, resolve_equipment)

IF_PATH = "ml/isolation_forest.pkl"

_bundle: dict = None

_LABELS = {
    "temperature": ("sıcaklık", "°C", 1),
    "vibration":   ("titreşim", "mm/s", 2),
    "pressure":    ("basınç", "bar", 2),
    "current":     ("akım", "A", 1),
    "speed":       ("hız", "", 1),
}


def build_features(z: np.ndarray) -> np.ndarray:
    """(n, 5) z-skor → (n, 7) model girdisi: z, max|z|, ||z||."""
    z = np.atleast_2d(z)
    return np.c_[z, np.abs(z).max(axis=1), np.linalg.norm(z, axis=1)]


def fit_isolation_forest(n_samples: int = 8000, seed: int = 42) -> dict:
    """
    Modeli yalnızca normal çalışma verisiyle eğitir (yenilik tespiti).
    Karar eşiği, normal verinin en uç %0.3'lük dilimine oturur; skor ölçeği
    normal verinin karar fonksiyonu dağılımından kalibre edilir.
    """
    from sklearn.ensemble import IsolationForest
    from data.simulator import _normal_reading

    state = np.random.get_state()
    np.random.seed(seed)
    try:
        rows = []
        ids = list(EQUIPMENT_PROFILES)
        for i in range(n_samples):
            eq_id = ids[i % len(ids)]
            r = _normal_reading(EQUIPMENT_PROFILES[eq_id])
            rows.append(normalize([r[k] for k in FEATURES], eq_id))
    finally:
        np.random.set_state(state)
    X = build_features(np.array(rows))

    model = IsolationForest(n_estimators=300, max_samples=2048,
                            contamination=0.003, random_state=seed)
    model.fit(X)
    scale = float(np.percentile(model.decision_function(X), 99))
    return {"model": model, "score_scale": max(scale, 1e-6), "features": FEATURES}


def save_bundle(bundle: dict, path: str = IF_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(bundle, f)


def _load():
    global _bundle
    if _bundle is None:
        loaded = None
        if os.path.exists(IF_PATH):
            with open(IF_PATH, "rb") as f:
                loaded = pickle.load(f)
        if not isinstance(loaded, dict) or "score_scale" not in loaded:
            loaded = fit_isolation_forest()
            save_bundle(loaded)
        _bundle = loaded
    return _bundle


def detect(reading: Dict) -> Dict:
    bundle = _load()
    eq_id = resolve_equipment(reading.get("equipment_id"), reading.get("equipment_type"))
    if eq_id is None:
        raise ValueError(f"Bilinmeyen ekipman: {reading.get('equipment_id')}")

    z = normalize([reading[k] for k in FEATURES], eq_id).reshape(1, -1)
    decision = float(bundle["model"].decision_function(build_features(z))[0])   # < 0 → anomali

    # 0.5 karar eşiğidir: normal okumalar 0–0.5, anomaliler 0.5–1 aralığına düşer.
    score = float(np.clip(0.5 - decision / (2 * bundle["score_scale"]), 0.0, 1.0))
    is_anomaly = decision < 0

    return {
        "is_anomaly":    bool(is_anomaly),
        "anomaly_score": round(score, 4),
        "description":   _describe(reading, eq_id, z[0], score) if is_anomaly else None,
    }


def _describe(reading: Dict, eq_id: str, z: np.ndarray, score: float) -> str:
    """Normal aralığın dışına çıkan sensörleri, sapma büyüklüğüne göre sıralı yazar."""
    profile = EQUIPMENT_PROFILES[eq_id]
    crit = critical_thresholds(eq_id)
    issues = []
    for i in np.argsort(-np.abs(z)):
        key = FEATURES[i]
        if abs(z[i]) < 3.5:
            continue
        name, unit, digits = _LABELS[key]
        val = reading[key]
        lo, hi = profile[key]
        if z[i] > 0:
            level = "kritik" if key in crit and val >= crit[key] else "yüksek"
        else:
            level = "düşük"
        issues.append(f"{level} {name} ({val:.{digits}f} {unit}".rstrip()
                      + f"; normal {lo:g}–{hi:g})")
    if not issues:
        issues.append("çoklu parametre sapması")
    return f"Anomali: {', '.join(issues[:3])} — skor {score:.2f}"
