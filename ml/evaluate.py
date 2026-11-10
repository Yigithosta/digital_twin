"""
Model Doğrulama — Isolation Forest (anomali tespiti)
-----------------------------------------------------
Model, sistemin gerçekte işlediği veri dağılımında (saha simülatörü; canlı MQTT
akışıyla aynı üretici) eğitimden bağımsız, etiketli bir test kümesinde
değerlendirilir. Sonuçlar simülasyon verisine aittir; saha verisiyle yeniden
doğrulanmalıdır.

Çalıştırma: python ml/evaluate.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from sklearn.metrics import (accuracy_score, classification_report,
                             confusion_matrix, roc_auc_score)

from app.services.anomaly_detector import _load, build_features
from data.simulator import (EQUIPMENT_PROFILES, FEATURES, _anomaly_reading,
                            _normal_reading, normalize)

N_TEST    = 20000
ANOM_RATE = 0.20          # test kümesinde arıza oranı
SEED      = 20260703      # eğitim tohumundan (42) farklı


def evaluate() -> dict:
    np.random.seed(SEED)
    ids = list(EQUIPMENT_PROFILES)
    Z, y = [], []
    for _ in range(N_TEST):
        eq_id = ids[np.random.randint(len(ids))]
        is_anom = np.random.random() < ANOM_RATE
        r = (_anomaly_reading if is_anom else _normal_reading)(EQUIPMENT_PROFILES[eq_id])
        Z.append(normalize([r[f] for f in FEATURES], eq_id))
        y.append(int(is_anom))
    y = np.array(y)

    decision = _load()["model"].decision_function(build_features(np.array(Z)))
    y_pred = (decision < 0).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()

    return {
        "n": N_TEST, "anomaly_rate": float(y.mean()),
        "accuracy": accuracy_score(y, y_pred),
        "roc_auc": roc_auc_score(y, -decision),
        "recall": tp / (tp + fn), "precision": tp / (tp + fp),
        "false_alarm_rate": fp / (fp + tn),
        "confusion": (tn, fp, fn, tp),
        "report": classification_report(y, y_pred, target_names=["Normal", "Arıza"], digits=3),
    }


if __name__ == "__main__":
    m = evaluate()
    tn, fp, fn, tp = m["confusion"]
    print("=" * 56)
    print("  Isolation Forest — Model Doğrulama (simülatör verisi)")
    print("=" * 56)
    print(f"  Test örneği: {m['n']}  ·  arıza oranı: %{m['anomaly_rate'] * 100:.1f}\n")
    print(m["report"])
    print("Karmaşıklık Matrisi:")
    print(f"  Gerçek Normal → Tahmin Normal : {tn:6d}")
    print(f"  Gerçek Normal → Tahmin Arıza  : {fp:6d}  (yanlış alarm)")
    print(f"  Gerçek Arıza  → Tahmin Normal : {fn:6d}  (kaçırılan)")
    print(f"  Gerçek Arıza  → Tahmin Arıza  : {tp:6d}\n")
    print(f"  Doğruluk            : %{m['accuracy'] * 100:.1f}")
    print(f"  ROC-AUC             : {m['roc_auc']:.3f}")
    print(f"  Duyarlılık (recall) : %{m['recall'] * 100:.1f}  — yakalanan arıza oranı")
    print(f"  Kesinlik            : %{m['precision'] * 100:.1f}  — alarmların isabet oranı")
    print(f"  Yanlış alarm oranı  : %{m['false_alarm_rate'] * 100:.2f}")
    print("=" * 56)
