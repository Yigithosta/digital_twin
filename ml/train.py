"""
Model Eğitimi
-------------
Çalıştırma: python ml/train.py

1. Isolation Forest  → gerçek Kaggle verisiyle eğitilir
2. LSTM              → simüle zaman serisiyle eğitilir
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
import pickle
import torch
import torch.nn as nn
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

DATA_PATH  = "data/predictive_maintenance.csv"
IF_PATH    = "ml/isolation_forest.pkl"
SCALER_PATH = "ml/scaler.pkl"
LSTM_PATH  = "ml/lstm_model.pt"


# ─────────────────────────────────────────────
# 1. Isolation Forest
# ─────────────────────────────────────────────

def train_isolation_forest():
    print("── Isolation Forest eğitiliyor ──")

    # Kaggle'dan arıza oranını öğren
    df_kaggle = pd.read_csv(DATA_PATH)
    contamination = float(df_kaggle["Target"].mean())  # ~%3.4
    print(f"  Kaggle arıza oranı  : %{contamination*100:.1f}")

    # Simülatörden gerçekçi sensör verisi üret (ekipman ölçek aralıkları doğru)
    from data.simulator import generate_training_data
    df_sim = generate_training_data(n_samples=5000)

    features = ["temperature", "vibration", "pressure", "current", "speed"]
    X = df_sim[features].values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=42,
    )
    model.fit(X_scaled)

    os.makedirs("ml", exist_ok=True)
    with open(IF_PATH, "wb") as f:
        pickle.dump(model, f)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)

    preds    = model.predict(X_scaled)
    detected = (preds == -1).sum()
    print(f"  Eğitim verisi       : {len(df_sim)} örnek (simüle)")
    print(f"  Tespit edilen       : {detected} anomali")
    print(f"  Model kaydedildi    : {IF_PATH}")


# ─────────────────────────────────────────────
# 2. LSTM
# ─────────────────────────────────────────────

SEQ_LEN    = 20
INPUT_SIZE = 5
HIDDEN     = 64
LAYERS     = 2
EPOCHS     = 50


class LSTMModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(INPUT_SIZE, HIDDEN, LAYERS,
                            batch_first=True, dropout=0.2)
        self.fc   = nn.Linear(HIDDEN, INPUT_SIZE)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])


def _make_sequences(data: np.ndarray):
    X, y = [], []
    for i in range(len(data) - SEQ_LEN):
        X.append(data[i : i + SEQ_LEN])
        y.append(data[i + SEQ_LEN])
    return np.array(X), np.array(y)


LSTM_SCALER_PATH = "ml/lstm_scaler.pkl"
BATCH_SIZE = 128


def train_lstm():
    print("\n── LSTM eğitiliyor (simülatör verisi) ──")

    from data.simulator import generate_training_data
    # 3000 örnek, simülatörden
    df = generate_training_data(n_samples=3000)

    features = ["temperature", "vibration", "pressure", "current", "speed"]

    scaler = StandardScaler()
    data_scaled = scaler.fit_transform(df[features].values)

    with open(LSTM_SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)
    print(f"  LSTM scaler kaydedildi: {LSTM_SCALER_PATH}")

    X_all, y_all = _make_sequences(data_scaled)
    print(f"  Dizi sayısı: {len(X_all)}")

    # CPU kullan (MPS için bellek taşması önlenir)
    device = torch.device("cpu")
    print(f"  Cihaz: {device}")

    X_t = torch.tensor(X_all, dtype=torch.float32)
    y_t = torch.tensor(y_all, dtype=torch.float32)

    dataset   = torch.utils.data.TensorDataset(X_t, y_t)
    loader    = torch.utils.data.DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    model     = LSTMModel().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.MSELoss()

    model.train()
    for epoch in range(1, EPOCHS + 1):
        epoch_loss = 0.0
        for xb, yb in loader:
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
        if epoch % 10 == 0:
            print(f"  Epoch {epoch:3d}/{EPOCHS} — Loss: {epoch_loss/len(loader):.5f}")

    torch.save(model.state_dict(), LSTM_PATH)
    print(f"  Model kaydedildi: {LSTM_PATH}")


# ─────────────────────────────────────────────
# 3. RUL (Kalan Faydalı Ömür) — LSTM Regresör
# ─────────────────────────────────────────────

RUL_PATH        = "ml/rul_lstm.pt"
RUL_SCALER_PATH = "ml/rul_scaler.pkl"
RUL_MAX_HOURS   = 100.0   # etiket normalizasyonu için tavan
RUL_EPOCHS      = 40


class RULModel(nn.Module):
    """Sensör penceresi → kalan faydalı ömür (normalize 0-1)."""
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(INPUT_SIZE, HIDDEN, LAYERS,
                            batch_first=True, dropout=0.2)
        self.fc   = nn.Linear(HIDDEN, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return torch.sigmoid(self.fc(out[:, -1, :]))   # [0,1]


def _rul_sequences(run: np.ndarray, rul: np.ndarray):
    """Tek bir run-to-failure trajektorisinden (pencere → RUL) çiftleri."""
    X, y = [], []
    for i in range(len(run) - SEQ_LEN):
        X.append(run[i : i + SEQ_LEN])
        y.append(rul[i + SEQ_LEN - 1])   # pencere sonundaki RUL
    return X, y


def train_rul():
    print("\n── RUL (Kalan Faydalı Ömür) modeli eğitiliyor ──")
    from data.simulator import generate_rul_dataset

    df = generate_rul_dataset(runs_per_equipment=40)
    features = ["temperature", "vibration", "pressure", "current", "speed"]

    # Tüm run'lar üzerinde tek scaler
    scaler = StandardScaler()
    scaler.fit(df[features].values)
    with open(RUL_SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)
    print(f"  RUL scaler kaydedildi: {RUL_SCALER_PATH}")

    # Her bağımsız run'ı run_id'ye göre ayrı işle (pencereler run sınırını aşmasın).
    X_all, y_all = [], []
    feat_scaled = scaler.transform(df[features].values)
    rul_vals = df["rul_hours"].values
    n_runs = 0
    for _, idx in df.groupby("run_id").groups.items():
        idx = list(idx)
        run = feat_scaled[idx]
        rul = np.clip(rul_vals[idx] / RUL_MAX_HOURS, 0, 1)
        if len(run) > SEQ_LEN:
            xs, ys = _rul_sequences(run, rul)
            X_all.extend(xs); y_all.extend(ys)
            n_runs += 1

    X_all = np.array(X_all, dtype=np.float32)
    y_all = np.array(y_all, dtype=np.float32).reshape(-1, 1)
    print(f"  Eğitim penceresi: {len(X_all)} (run sayısı: {n_runs})")

    device = torch.device("cpu")
    X_t = torch.tensor(X_all)
    y_t = torch.tensor(y_all)
    loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(X_t, y_t),
        batch_size=BATCH_SIZE, shuffle=True,
    )

    model     = RULModel().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.MSELoss()

    model.train()
    for epoch in range(1, RUL_EPOCHS + 1):
        ep = 0.0
        for xb, yb in loader:
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
            ep += loss.item()
        if epoch % 10 == 0:
            # MAE'yi saat cinsine çevir
            mae_h = (ep / len(loader)) ** 0.5 * RUL_MAX_HOURS
            print(f"  Epoch {epoch:3d}/{RUL_EPOCHS} — Loss: {ep/len(loader):.5f}  (~RMSE {mae_h:.1f} saat)")

    torch.save(model.state_dict(), RUL_PATH)
    print(f"  Model kaydedildi: {RUL_PATH}")


# ─────────────────────────────────────────────

if __name__ == "__main__":
    train_isolation_forest()
    train_lstm()
    train_rul()
    print("\nEğitim tamamlandı.")
