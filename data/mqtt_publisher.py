"""
MQTT Sensör Yayıncısı
---------------------
Maden sahasındaki fiziksel sensörleri taklit eder; her ekipman için üretilen
okumaları MQTT broker'a (Mosquitto) yayınlar.

Topic:   maden/{equipment_id}/sensor
Payload: {"equipment_id", "equipment_type", "temperature", ...} (JSON)

Gerçek sahada bu dosyanın yerini PLC/sensörlere bağlı bir gateway alır;
backend tarafı (mqtt_subscriber) değişmeden aynı veriyi tüketir.

Tek başına çalıştırma:
    python -m data.mqtt_publisher
"""

import json
import os
import time

import paho.mqtt.client as mqtt

from data.simulator import EQUIPMENT_PROFILES, LiveSimulator

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
TOPIC_TMPL = "maden/{equipment_id}/sensor"

EQUIPMENT_IDS = list(EQUIPMENT_PROFILES.keys())

_sim = LiveSimulator()


def make_client(client_id: str = "maden-publisher") -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
    )
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
    return client


def publish_reading(client: mqtt.Client, equipment_id: str,
                    force_anomaly: bool = False, force_gas: bool = False) -> dict:
    """Bir ekipman için okuma üretir ve MQTT'ye yayınlar. Üretilen okumayı döner."""
    reading = _sim.step(equipment_id, force_anomaly=force_anomaly, force_gas=force_gas)
    client.publish(TOPIC_TMPL.format(equipment_id=equipment_id), json.dumps(reading), qos=1)
    return reading


def run_loop(interval: float = 5.0):
    client = make_client()
    client.loop_start()
    print(f"MQTT yayıncısı başladı → {MQTT_HOST}:{MQTT_PORT}")
    try:
        while True:
            for eq_id in EQUIPMENT_IDS:
                r = publish_reading(client, eq_id)
                print(f"  → maden/{eq_id}/sensor  sıcaklık={r['temperature']:.1f} titreşim={r['vibration']:.2f}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nYayıncı durduruldu.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    run_loop()
