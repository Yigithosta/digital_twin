"""
Model Doğrulama
---------------
Çalıştırma: python ml/evaluate.py
"""

import sys, os, pickle
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score

# ── Veri ──────────────────────────────────────────────
df = pd.read_csv("data/predictive_maintenance.csv")
df["temperature"] = df["Air temperature [K]"] - 273.15
df["vibration"]   = df["Tool wear [min]"]
df["speed"]       = df["Rotational speed [rpm]"]
df["current"]     = df["Torque [Nm]"]
df["pressure"]    = (df["current"] / df["current"].max()) * 10

features = ["temperature", "vibration", "pressure", "current", "speed"]
X = df[features].values
y = df["Target"].values

# ── Model yükle ────────────────────────────────────────
with open("ml/scaler.pkl", "rb") as f:
    scaler = pickle.load(f)
with open("ml/isolation_forest.pkl", "rb") as f:
    model = pickle.load(f)

X_scaled = scaler.transform(X)
preds    = model.predict(X_scaled)
y_pred   = (preds == -1).astype(int)
scores   = -model.score_samples(X_scaled)

# ── Sonuçlar ───────────────────────────────────────────
print("=" * 50)
print("   Isolation Forest — Model Doğrulama")
print("=" * 50)

print(classification_report(y, y_pred, target_names=["Normal", "Arıza"], digits=3))

cm = confusion_matrix(y, y_pred)
tp, fn, fp, tn = cm[1][1], cm[1][0], cm[0][1], cm[0][0]

print("Karmaşıklık Matrisi:")
print(f"  Gerçek Normal → Tahmin Normal : {tn:5d}  ✓")
print(f"  Gerçek Normal → Tahmin Arıza  : {fp:5d}  (Yanlış Alarm)")
print(f"  Gerçek Arıza  → Tahmin Normal : {fn:5d}  (Kaçırılan)")
print(f"  Gerçek Arıza  → Tahmin Arıza  : {tp:5d}  ✓")

print()
print(f"Genel Doğruluk : %{(tp+tn)/(tp+tn+fp+fn)*100:.1f}")
print(f"ROC-AUC Skoru  : {roc_auc_score(y, scores):.4f}")
print(f"Hassasiyet     : %{tp/(tp+fn)*100:.1f}  — arızaların kaçı yakalandı")
print(f"Özgüllük       : %{tn/(tn+fp)*100:.1f}  — normallerin kaçı doğru")
print("=" * 50)
