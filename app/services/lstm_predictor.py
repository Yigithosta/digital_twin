"""
LSTM tabanlı zaman serisi tahmini.
Bir sonraki sensör değerlerini tahmin eder.
"""

import torch
import torch.nn as nn
import numpy as np
import pickle
import os
from typing import List

LSTM_PATH        = "ml/lstm_model.pt"
LSTM_SCALER_PATH = "ml/lstm_scaler.pkl"
RUL_PATH         = "ml/rul_lstm.pt"
RUL_SCALER_PATH  = "ml/rul_scaler.pkl"
RUL_MAX_HOURS    = 100.0
SEQ_LEN    = 20
INPUT_SIZE = 5
HIDDEN     = 64
LAYERS     = 2

_device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
_model      = None
_scaler     = None
_rul_model  = None
_rul_scaler = None


class LSTMModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(INPUT_SIZE, HIDDEN, LAYERS,
                            batch_first=True, dropout=0.2)
        self.fc   = nn.Linear(HIDDEN, INPUT_SIZE)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


class RULModel(nn.Module):
    """Sensör penceresi → kalan faydalı ömür (normalize 0-1)."""
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(INPUT_SIZE, HIDDEN, LAYERS,
                            batch_first=True, dropout=0.2)
        self.fc   = nn.Linear(HIDDEN, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return torch.sigmoid(self.fc(out[:, -1, :]))


def _load():
    global _model, _scaler
    if _model is None:
        m = LSTMModel().to(_device)
        if os.path.exists(LSTM_PATH):
            m.load_state_dict(torch.load(LSTM_PATH, map_location=_device))
        m.eval()
        _model = m
    if _scaler is None and os.path.exists(LSTM_SCALER_PATH):
        with open(LSTM_SCALER_PATH, "rb") as f:
            _scaler = pickle.load(f)


def _load_rul():
    global _rul_model, _rul_scaler
    if _rul_model is None:
        m = RULModel().to(_device)
        if os.path.exists(RUL_PATH):
            m.load_state_dict(torch.load(RUL_PATH, map_location=_device))
        m.eval()
        _rul_model = m
    if _rul_scaler is None and os.path.exists(RUL_SCALER_PATH):
        with open(RUL_SCALER_PATH, "rb") as f:
            _rul_scaler = pickle.load(f)


def predict(sequence: List[List[float]]) -> dict:
    """
    sequence: [[temp, vib, pres, cur, spd], ...] — en az SEQ_LEN adım
    Döner: bir sonraki adımın tahmin değerleri (gerçek birimlerle)
    """
    _load()
    if len(sequence) < SEQ_LEN:
        return {"error": f"En az {SEQ_LEN} adım gerekli"}

    arr = np.array(sequence[-SEQ_LEN:], dtype=np.float32)
    if _scaler is not None:
        arr = _scaler.transform(arr)

    x = torch.tensor([arr], dtype=torch.float32).to(_device)
    with torch.no_grad():
        pred = _model(x).cpu().numpy()[0]

    if _scaler is not None:
        pred = _scaler.inverse_transform([pred])[0]

    keys = ["temperature", "vibration", "pressure", "current", "speed"]
    return {k: round(float(v), 3) for k, v in zip(keys, pred)}


def _dominant_sensor(last_reading: dict, equipment_id: str):
    """Kritik eşiğe en çok yaklaşan sensörü ve doluluk oranını döner."""
    from data.simulator import critical_thresholds, EQUIPMENT_PROFILES
    crit    = critical_thresholds(equipment_id)
    profile = EQUIPMENT_PROFILES[equipment_id]
    labels  = {"temperature": "Sıcaklık", "vibration": "Titreşim",
               "current": "Akım", "pressure": "Basınç"}
    worst, worst_ratio = None, -1.0
    for key in ["temperature", "vibration", "current"]:
        hi = profile[key][1]
        val = last_reading.get(key, hi)
        ratio = (val - hi) / (crit[key] - hi) if crit[key] > hi else 0.0
        if ratio > worst_ratio:
            worst, worst_ratio = key, ratio
    return labels.get(worst, worst), max(0.0, min(1.0, worst_ratio)), crit


def predict_rul(sequence: List[List[float]], equipment_id: str) -> dict:
    """
    Kalan Faydalı Ömür (RUL) tahmini.
    sequence: [[temp, vib, pres, cur, spd], ...] — son SEQ_LEN okuma
    Döner: rul_saat, saglik_yuzde, durum, baskin_sensor, öneri.
    """
    _load_rul()
    if len(sequence) < SEQ_LEN:
        return {"hata": f"En az {SEQ_LEN} okuma gerekli (mevcut: {len(sequence)})"}

    arr = np.array(sequence[-SEQ_LEN:], dtype=np.float32)
    if _rul_scaler is not None:
        arr = _rul_scaler.transform(arr)

    x = torch.tensor([arr], dtype=torch.float32).to(_device)
    with torch.no_grad():
        norm = float(_rul_model(x).cpu().numpy()[0][0])

    rul_hours = round(norm * RUL_MAX_HOURS, 1)
    health    = round(min(100.0, norm * 100.0 / 0.6), 1)   # ~60h ve üzeri = tam sağlık
    health    = min(100.0, health)

    keys = ["temperature", "vibration", "pressure", "current", "speed"]
    last = dict(zip(keys, sequence[-1]))
    sensor, ratio, crit = _dominant_sensor(last, equipment_id)

    if rul_hours < 8:
        durum, renk = "KRİTİK", "kirmizi"
        oneri = f"Acil bakım planlayın. {sensor} kritik eşiğe çok yakın. Müdahale hedefi: <15 dk."
    elif rul_hours < 24:
        durum, renk = "UYARI", "sari"
        oneri = f"24 saat içinde bakım planlanmalı. {sensor} trendi yükseliyor."
    else:
        durum, renk = "SAĞLIKLI", "yesil"
        oneri = "Tüm parametreler normal. Planlı bakım takvimine uyun."

    return {
        "equipment_id":   equipment_id,
        "rul_saat":       rul_hours,
        "rul_gun":        round(rul_hours / 24, 1),
        "saglik_yuzde":   health,
        "durum":          durum,
        "renk":           renk,
        "baskin_sensor":  sensor,
        "sensor_doluluk": round(ratio * 100, 1),   # kritik eşiğe % yakınlık
        "oneri":          oneri,
    }
