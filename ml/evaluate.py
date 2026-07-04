"""
Model Doğrulama — Isolation Forest (anomali tespiti)
-----------------------------------------------------
Model, sistemin gerçekte işlediği veri dağılımında (Digital Twin simülatörü;
canlı MQTT akışıyla aynı üretici) etiketli bir test kümesi üzerinde değerlendirilir.
Bu, modelin sahadaki gerçek performansını yansıtan doğru değerlendirmedir.

Çalıştırma: python3 ml/evaluate.py
"""

import sys, os, pickle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from sklearn.metrics import (classification_report, confusion_matrix,
                             roc_auc_score, accuracy_score)
from data.simulator import _normal_reading, _anomaly_reading, EQUIPMENT_PROFILES

FEATURES = ["temperature", "vibration", "pressure", "current", "speed"]
N_TEST   = 4000
ANOM_RATE = 0.20          # test kümesinde arıza oranı
SEED     = 20260703

# ── Etiketli, bağımsız test kümesi üret (eğitimden ayrı) ──────────────────────
rng = np.random.default_rng(SEED)
profiles = list(EQUIPMENT_PROFILES.values())
X, y = [], []
for _ in range(N_TEST):
    prof = profiles[rng.integers(len(profiles))]
    is_anom = rng.random() < ANOM_RATE
    r = _anomaly_reading(prof) if is_anom else _normal_reading(prof)
    X.append([r[f] for f in FEATURES])
    y.append(int(is_anom))
X = np.array(X); y = np.array(y)

# ── Model + scaler ────────────────────────────────────────────────────────────
with open("ml/scaler.pkl", "rb") as f:
    scaler = pickle.load(f)
with open("ml/isolation_forest.pkl", "rb") as f:
    model = pickle.load(f)

Xs      = scaler.transform(X)
y_pred  = (model.predict(Xs) == -1).astype(int)
scores  = -model.score_samples(Xs)     # yüksek = daha anormal

# ── Sonuçlar ──────────────────────────────────────────────────────────────────
print("=" * 52)
print("   Isolation Forest — Model Doğrulama (simülatör domaini)")
print("=" * 52)
print(f"  Test örneği: {N_TEST}  ·  gerçek arıza oranı: %{y.mean()*100:.1f}\n")
print(classification_report(y, y_pred, target_names=["Normal", "Arıza"], digits=3))

cm = confusion_matrix(y, y_pred)
tn, fp, fn, tp = cm.ravel()
print("Karmaşıklık Matrisi:")
print(f"  Gerçek Normal → Tahmin Normal : {tn:5d}  (dogru)")
print(f"  Gerçek Normal → Tahmin Arıza  : {fp:5d}  (yanlış alarm)")
print(f"  Gerçek Arıza  → Tahmin Normal : {fn:5d}  (kaçırılan)")
print(f"  Gerçek Arıza  → Tahmin Arıza  : {tp:5d}  (dogru)\n")

print(f"  Genel Doğruluk (Accuracy) : %{accuracy_score(y, y_pred)*100:.1f}")
print(f"  ROC-AUC Skoru             : {roc_auc_score(y, scores):.3f}")
print(f"  Hassasiyet (Recall/Arıza) : %{tp/(tp+fn)*100:.1f}  — arızaların yakalanma oranı")
print(f"  Kesinlik (Precision/Arıza): %{tp/(tp+fp)*100:.1f}  — arıza dedik, gerçekten arıza")
print(f"  Özgüllük (Specificity)    : %{tn/(tn+fp)*100:.1f}  — normallerin doğru geçme oranı")
print("=" * 52)
