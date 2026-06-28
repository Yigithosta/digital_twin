"""
Isolation Forest tabanlı anomali tespiti.
Model ml/train.py ile eğitilir, buradan yüklenir.
"""

import numpy as np
import pickle
import os
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from typing import Dict

IF_PATH     = "ml/isolation_forest.pkl"
SCALER_PATH = "ml/scaler.pkl"

_model:  IsolationForest  = None
_scaler: StandardScaler   = None


def _load():
    global _model, _scaler
    if _model is None:
        if os.path.exists(IF_PATH) and os.path.exists(SCALER_PATH):
            with open(IF_PATH,     "rb") as f: _model  = pickle.load(f)
            with open(SCALER_PATH, "rb") as f: _scaler = pickle.load(f)
        else:
            _bootstrap()


def _bootstrap():
    """Eğitilmiş model yoksa Kaggle verisiyle hızlıca eğit."""
    global _model, _scaler
    import pandas as pd
    from sklearn.preprocessing import StandardScaler

    DATA = "data/predictive_maintenance.csv"
    if not os.path.exists(DATA):
        raise FileNotFoundError(f"{DATA} bulunamadı. Önce ml/train.py çalıştırın.")

    df = pd.read_csv(DATA)
    df["temperature"] = df["Air temperature [K]"]  - 273.15
    df["vibration"]   = df["Tool wear [min]"]
    df["speed"]       = df["Rotational speed [rpm]"]
    df["current"]     = df["Torque [Nm]"]
    df["pressure"]    = (df["current"] / df["current"].max()) * 10

    X = df[["temperature", "vibration", "pressure", "current", "speed"]].values
    _scaler = StandardScaler()
    X_s = _scaler.fit_transform(X)

    _model = IsolationForest(
        n_estimators=200,
        contamination=float(df["Target"].mean()),
        random_state=42,
    )
    _model.fit(X_s)

    os.makedirs("ml", exist_ok=True)
    with open(IF_PATH,     "wb") as f: pickle.dump(_model,  f)
    with open(SCALER_PATH, "wb") as f: pickle.dump(_scaler, f)


def detect(reading: Dict) -> Dict:
    _load()

    x = np.array([[
        reading["temperature"],
        reading["vibration"],
        reading["pressure"],
        reading["current"],
        reading["speed"],
    ]])
    x_scaled   = _scaler.transform(x)
    prediction = _model.predict(x_scaled)[0]
    raw_score  = float(_model.score_samples(x_scaled)[0])

    # score_samples: daha negatif → daha anormal
    # −0.5 eşiğini baz alarak 0-1'e normalize et
    normalized = float(np.clip(1 - (raw_score + 0.5), 0.0, 1.0))
    is_anomaly = prediction == -1

    return {
        "is_anomaly":    bool(is_anomaly),
        "anomaly_score": round(normalized, 4),
        "description":   _describe(reading, normalized) if is_anomaly else None,
    }


def _describe(r: Dict, score: float) -> str:
    issues = []
    if r["temperature"] > 35:   issues.append(f"yüksek sıcaklık ({r['temperature']:.1f}°C)")
    if r["vibration"]   > 200:  issues.append(f"aşırı takım aşınması ({r['vibration']:.0f} dk)")
    if r["current"]     > 60:   issues.append(f"yüksek tork ({r['current']:.1f} Nm)")
    if r["pressure"]    > 8:    issues.append(f"yüksek basınç ({r['pressure']:.1f} bar)")
    if not issues:               issues.append("çoklu parametre sapması")
    return f"Anomali: {', '.join(issues)} — skor {score:.3f}"
