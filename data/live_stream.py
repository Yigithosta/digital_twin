"""
Canlı sensör verisi üretici.
FastAPI çalışırken terminalde çalıştırın:
  python data/live_stream.py

Her 5 saniyede 3 ekipman için yeni okuma gönderir.
Grafana ve demo arayüzü otomatik güncellenir.
"""
import time
import urllib.request
import json
import random

API = "http://localhost:8000"
EQUIPMENT = ["conveyor_01", "pump_01", "crusher_01"]

print("Canlı veri akışı başladı. Durdurmak için Ctrl+C\n")

cycle = 0
while True:
    cycle += 1
    # Her 20 döngüde bir zorunlu anomali
    force_anomaly = (cycle % 20 == 0)

    for eq_id in EQUIPMENT:
        url = f"{API}/sensors/simulate/{eq_id}"
        if force_anomaly and eq_id == random.choice(EQUIPMENT):
            url += "?force_anomaly=true"

        try:
            req = urllib.request.Request(url, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                status = "⚠ ANOMALİ" if data.get("is_anomaly") else "  Normal "
                print(f"[{eq_id:<12}] {status} | "
                      f"Sıcaklık: {data['temperature']:5.1f}°C | "
                      f"Titreşim: {data['vibration']:5.2f} | "
                      f"Skor: {data['anomaly_score']:.3f}")
        except Exception as e:
            print(f"[{eq_id}] Hata: {e}")

    print()
    time.sleep(5)
