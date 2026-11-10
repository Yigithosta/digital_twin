"""
Model Eğitimi
-------------
Çalıştırma: python ml/train.py

1. Isolation Forest → normal çalışma verisiyle (yenilik tespiti)
2. LSTM tahminci    → bir sonraki sensör okuması
3. LSTM RUL         → arızaya kadar (run-to-failure) serilerden kalan faydalı ömür

Tüm modeller ekipman profiline göre normalize edilmiş özelliklerle eğitilir.
Doğrulama metrikleri, eğitimde kullanılmayan serilerde hesaplanır.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import torch
import torch.nn as nn

from app.services.anomaly_detector import IF_PATH, fit_isolation_forest, save_bundle
from app.services.lstm_predictor import (LSTM_PATH, RUL_MAX_HOURS, RUL_PATH, SEQ_LEN,
                                         LSTMModel, RULModel)
from data.simulator import (EQUIPMENT_PROFILES, FEATURES, LiveSimulator,
                            generate_degradation_run, generate_rul_dataset, normalize)

SEED       = 42
BATCH_SIZE = 128
EPOCHS     = 30
RUL_EPOCHS = 40


def _loader(X, y, shuffle=True):
    ds = torch.utils.data.TensorDataset(torch.tensor(X), torch.tensor(y))
    return torch.utils.data.DataLoader(ds, batch_size=BATCH_SIZE, shuffle=shuffle)


def _fit(model, train, epochs, label):
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = nn.MSELoss()
    for epoch in range(1, epochs + 1):
        model.train()
        total = 0.0
        for xb, yb in train:
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
            total += loss.item()
        if epoch % 10 == 0:
            print(f"  {label} epoch {epoch:3d}/{epochs} — kayıp: {total / len(train):.5f}")
    return model.eval()


# ── 1. Isolation Forest ──────────────────────────────────────────────────────

def train_isolation_forest():
    print("── Isolation Forest eğitiliyor ──")
    bundle = fit_isolation_forest(seed=SEED)
    save_bundle(bundle)
    print(f"  Model kaydedildi: {IF_PATH}  (skor ölçeği {bundle['score_scale']:.3f})")


# ── 2. LSTM tahminci ─────────────────────────────────────────────────────────

def _windows(series: np.ndarray):
    X = [series[i:i + SEQ_LEN] for i in range(len(series) - SEQ_LEN)]
    y = [series[i + SEQ_LEN] for i in range(len(series) - SEQ_LEN)]
    return X, y


def _forecast_series(steps_per_equipment: int, degradation_runs: int, seed: int):
    """Her ekipman için normal çalışma serisi + arızaya giden seriler (z-skor)."""
    sim = LiveSimulator(seed=seed)
    series = []
    for eq_id in EQUIPMENT_PROFILES:
        series.append(normalize(sim.sequence(eq_id, steps_per_equipment), eq_id))
        for _ in range(degradation_runs):
            run = generate_degradation_run(eq_id)
            series.append(normalize(run[FEATURES].values, eq_id))
    return series


def train_lstm():
    print("\n── LSTM tahminci eğitiliyor ──")
    X_tr, y_tr, X_va, y_va = [], [], [], []
    for s in _forecast_series(3000, 30, SEED):
        xs, ys = _windows(s)
        X_tr += xs; y_tr += ys
    for s in _forecast_series(600, 6, SEED + 1):
        xs, ys = _windows(s)
        X_va += xs; y_va += ys
    X_tr, y_tr = np.array(X_tr, dtype=np.float32), np.array(y_tr, dtype=np.float32)
    X_va, y_va = np.array(X_va, dtype=np.float32), np.array(y_va, dtype=np.float32)
    print(f"  Pencere: {len(X_tr)} eğitim · {len(X_va)} doğrulama")

    model = _fit(LSTMModel(), _loader(X_tr, y_tr), EPOCHS, "LSTM")
    with torch.no_grad():
        pred = model(torch.tensor(X_va)).numpy()
    rmse = float(np.sqrt(np.mean((pred - y_va) ** 2)))
    naive = float(np.sqrt(np.mean((X_va[:, -1, :] - y_va) ** 2)))   # son değeri tekrar et
    print(f"  Doğrulama RMSE: {rmse:.3f} sigma  (son-değer tahmini: {naive:.3f})")

    torch.save(model.state_dict(), LSTM_PATH)
    print(f"  Model kaydedildi: {LSTM_PATH}")
    return {"rmse": rmse, "naive_rmse": naive}


# ── 3. RUL (Kalan Faydalı Ömür) ──────────────────────────────────────────────

def train_rul():
    print("\n── RUL (Kalan Faydalı Ömür) modeli eğitiliyor ──")
    df = generate_rul_dataset(runs_per_equipment=40)

    # Run'lar bütün olarak ayrılır: doğrulama serileri eğitimde hiç görülmez.
    run_ids = df["run_id"].unique()
    rng = np.random.default_rng(SEED)
    rng.shuffle(run_ids)
    val_ids = set(run_ids[: len(run_ids) // 5])

    sets = {"tr": ([], []), "va": ([], [])}
    for run_id, run in df.groupby("run_id"):
        if len(run) <= SEQ_LEN:
            continue
        z = normalize(run[FEATURES].values, run["equipment_id"].iloc[0])
        rul = np.clip(run["rul_hours"].values / RUL_MAX_HOURS, 0, 1)
        X, y = sets["va" if run_id in val_ids else "tr"]
        for i in range(len(z) - SEQ_LEN):
            X.append(z[i:i + SEQ_LEN])
            y.append(rul[i + SEQ_LEN - 1])   # pencere sonundaki RUL

    X_tr = np.array(sets["tr"][0], dtype=np.float32)
    y_tr = np.array(sets["tr"][1], dtype=np.float32).reshape(-1, 1)
    X_va = np.array(sets["va"][0], dtype=np.float32)
    y_va = np.array(sets["va"][1], dtype=np.float32).reshape(-1, 1)
    print(f"  Pencere: {len(X_tr)} eğitim · {len(X_va)} doğrulama ({len(val_ids)} ayrı run)")

    model = _fit(RULModel(), _loader(X_tr, y_tr), RUL_EPOCHS, "RUL")
    with torch.no_grad():
        pred = model(torch.tensor(X_va)).numpy()
    err = np.abs(pred - y_va) * RUL_MAX_HOURS
    mae = float(err.mean())
    near = y_va * RUL_MAX_HOURS < 24          # bakım kararının verildiği bölge
    mae_near = float(err[near].mean())
    print(f"  Doğrulama MAE: {mae:.1f} saat  ·  son 24 saatte: {mae_near:.1f} saat")

    torch.save(model.state_dict(), RUL_PATH)
    print(f"  Model kaydedildi: {RUL_PATH}")
    return {"mae_hours": mae, "mae_last24h": mae_near}


if __name__ == "__main__":
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    train_isolation_forest()
    train_lstm()
    train_rul()
    for stale in ("ml/scaler.pkl", "ml/lstm_scaler.pkl", "ml/rul_scaler.pkl"):
        if os.path.exists(stale):
            os.remove(stale)
    print("\nEğitim tamamlandı.")
