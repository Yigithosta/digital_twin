"""
LSTM tabanlı kestirim modelleri.

  • LSTMModel : son SEQ_LEN okumadan bir sonraki okumayı tahmin eder (ileriye
                doğru yinelenerek kısa vadeli trend çıkarılır).
  • RULModel  : aynı pencereden Kalan Faydalı Ömrü (RUL) tahmin eder.

İki model de ekipman profiline göre normalize edilmiş (z-skor) girdilerle
çalışır; ayrı bir ölçekleyici dosyası gerekmez.
"""

import os
from typing import List

import numpy as np
import torch
import torch.nn as nn

from data.simulator import (EQUIPMENT_PROFILES, FEATURES, critical_thresholds,
                            denormalize, normalize)

LSTM_PATH     = "ml/lstm_model.pt"
RUL_PATH      = "ml/rul_lstm.pt"
RUL_MAX_HOURS = 100.0
SEQ_LEN    = 20
INPUT_SIZE = 5
HIDDEN     = 64
LAYERS     = 2

# Tek pencerelik çıkarım CPU'da milisaniyeler sürer; cihaz aktarımı gerekmez.
_device = torch.device("cpu")
_model = None
_rul_model = None


class LSTMModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(INPUT_SIZE, HIDDEN, LAYERS, batch_first=True, dropout=0.2)
        self.fc   = nn.Linear(HIDDEN, INPUT_SIZE)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


class RULModel(nn.Module):
    """Sensör penceresi → kalan faydalı ömür (normalize 0-1)."""
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(INPUT_SIZE, HIDDEN, LAYERS, batch_first=True, dropout=0.2)
        self.fc   = nn.Linear(HIDDEN, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return torch.sigmoid(self.fc(out[:, -1, :]))


def _load_weights(model: nn.Module, path: str) -> nn.Module:
    if not os.path.exists(path):
        raise FileNotFoundError(f"{path} bulunamadı. Önce `python ml/train.py` çalıştırın.")
    model.load_state_dict(torch.load(path, map_location=_device, weights_only=True))
    return model.to(_device).eval()


def _forecaster():
    global _model
    if _model is None:
        _model = _load_weights(LSTMModel(), LSTM_PATH)
    return _model


def _rul():
    global _rul_model
    if _rul_model is None:
        _rul_model = _load_weights(RULModel(), RUL_PATH)
    return _rul_model


def predict(sequence: List[List[float]], equipment_id: str, steps: int = 1) -> List[dict]:
    """
    sequence: [[temp, vib, pres, cur, spd], ...] — en az SEQ_LEN okuma (eskiden yeniye)
    Döner: sonraki `steps` adımın tahmini (gerçek birimlerle). Her adımda tahmin
    pencereye eklenerek ileri doğru yinelenir.
    """
    if len(sequence) < SEQ_LEN:
        raise ValueError(f"En az {SEQ_LEN} okuma gerekli (mevcut: {len(sequence)})")

    model = _forecaster()
    window = normalize(sequence[-SEQ_LEN:], equipment_id).astype(np.float32)
    out = []
    with torch.no_grad():
        for _ in range(steps):
            x = torch.from_numpy(window).unsqueeze(0).to(_device)
            nxt = model(x).cpu().numpy()[0]
            window = np.vstack([window[1:], nxt])
            values = denormalize(nxt, equipment_id)
            out.append({k: round(float(v), 3) for k, v in zip(FEATURES, values)})
    return out


def _dominant_sensor(last_reading: dict, equipment_id: str):
    """Kritik eşiğe en çok yaklaşan sensörü ve doluluk oranını döner."""
    crit    = critical_thresholds(equipment_id)
    profile = EQUIPMENT_PROFILES[equipment_id]
    labels  = {"temperature": "Sıcaklık", "vibration": "Titreşim", "current": "Akım"}
    worst, worst_ratio = None, -1.0
    for key in labels:
        hi = profile[key][1]
        val = last_reading.get(key, hi)
        ratio = (val - hi) / (crit[key] - hi) if crit[key] > hi else 0.0
        if ratio > worst_ratio:
            worst, worst_ratio = key, ratio
    # Basınç kaybı aşağı yönlü ilerler
    lo = profile["pressure"][0]
    loss = (lo - last_reading.get("pressure", lo)) / (lo - lo * 0.45)
    if loss > worst_ratio:
        return "Basınç kaybı", max(0.0, min(1.0, loss))
    return labels[worst], max(0.0, min(1.0, worst_ratio))


def predict_rul(sequence: List[List[float]], equipment_id: str) -> dict:
    """
    Kalan Faydalı Ömür (RUL) tahmini.
    sequence: [[temp, vib, pres, cur, spd], ...] — son SEQ_LEN okuma
    Döner: rul_saat, saglik_yuzde, durum, baskin_sensor, öneri.
    """
    if len(sequence) < SEQ_LEN:
        raise ValueError(f"En az {SEQ_LEN} okuma gerekli (mevcut: {len(sequence)})")

    window = normalize(sequence[-SEQ_LEN:], equipment_id).astype(np.float32)
    x = torch.from_numpy(window).unsqueeze(0).to(_device)
    with torch.no_grad():
        norm = float(_rul()(x).cpu().numpy()[0][0])

    rul_hours = round(norm * RUL_MAX_HOURS, 1)
    health    = round(min(100.0, norm * 100.0 / 0.6), 1)   # ~60 saat ve üzeri = tam sağlık

    last = dict(zip(FEATURES, sequence[-1]))
    sensor, ratio = _dominant_sensor(last, equipment_id)

    if rul_hours < 8:
        durum, renk = "KRİTİK", "kirmizi"
        oneri = f"Acil bakım planlayın. {sensor} kritik eşiğe çok yakın."
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
