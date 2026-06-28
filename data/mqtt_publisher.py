"""
MQTT Sensör Yayıncısı (Publisher)
----------------------------------
Maden sahasındaki fiziksel sensörleri taklit eder. Her ekipman için üretilen
sensör okumalarını MQTT broker'a (Mosquitto) yayınlar.

Topic yapısı:   maden/{equipment_id}/sensor
Payload (JSON): {"equipment_id", "equipment_type", "temperature", ...}

Gerçek sahada bu dosyanın yerini, PLC/sensörlere bağlı bir gateway alır;
backend tarafı (mqtt_subscriber) hiç değişmeden aynı veriyi tüketmeye devam eder.

Tek başına çalıştırma (manuel test):
    python data/mqtt_publisher.py
"""

import os
import json
import time
import paho.mqtt.client as mqtt

from data.simulator import generate_reading, EQUIPMENT_PROFILES

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
TOPIC_TMPL = "maden/{equipment_id}/sensor"

EQUIPMENT_IDS = list(EQUIPMENT_PROFILES.keys())


def make_client(client_id: str = "maden-publisher") -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
    )
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    return client


def publish_reading(client: mqtt.Client, equipment_id: str,
                    force_anomaly: bool = False, force_gas: bool = False) -> dict:
    """Bir ekipman için okuma üretir ve MQTT'ye yayınlar. Üretilen okumayı döner."""
    reading = generate_reading(equipment_id, force_anomaly=force_anomaly, force_gas=force_gas)
    topic = TOPIC_TMPL.format(equipment_id=equipment_id)
    client.publish(topic, json.dumps(reading), qos=1)
    return reading


def run_loop(interval: float = 8.0):
    """Sürekli yayın döngüsü (manuel test için)."""
    client = make_client()
    client.loop_start()
    print(f"MQTT publisher başladı → {MQTT_HOST}:{MQTT_PORT}")
    cycle = 0
    try:
        while True:
            cycle += 1
            # her 15 döngüde bir rastgele ekipmana anomali enjekte et
            force_eq = EQUIPMENT_IDS[cycle % len(EQUIPMENT_IDS)] if cycle % 15 == 0 else None
            for eq_id in EQUIPMENT_IDS:
                r = publish_reading(client, eq_id, force_anomaly=(eq_id == force_eq))
                print(f"  → maden/{eq_id}/sensor  temp={r['temperature']:.1f} vib={r['vibration']:.2f}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nPublisher durduruldu.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    run_loop()
