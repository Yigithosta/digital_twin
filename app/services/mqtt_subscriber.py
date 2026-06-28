"""
MQTT Sensör Abonesi (Subscriber)
---------------------------------
Backend'in veri giriş katmanı. Mosquitto broker'a abone olur, `maden/+/sensor`
topic'lerinden gelen her sensör mesajını alır ve işler:

    MQTT mesajı → anomali tespiti (Isolation Forest)
                → TimescaleDB'ye kayıt
                → Redis'e son durum (canlı dashboard)
                → anomali ise: AnomalyLog + n8n alarmı + Qdrant'a embedding

paho-mqtt kendi thread'inde (loop_start) çalışır. Gelen her mesaj,
asyncio.run_coroutine_threadsafe ile FastAPI'nin ana event loop'una aktarılır.
Böylece async DB/Redis işlemleri güvenle yürütülür.
"""

import os
import json
import asyncio
import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
TOPIC = "maden/+/sensor"

_client: mqtt.Client = None
_loop: asyncio.AbstractEventLoop = None


async def _handle_reading(reading: dict):
    """Tek bir sensör okumasını işler (ana event loop'ta çalışır)."""
    from datetime import datetime, timezone
    from app.database import AsyncSessionLocal
    from app.models.sensor import SensorReading, AnomalyLog
    from app.services.anomaly_detector import detect as detect_anomaly
    from app.services.n8n_notifier import notify
    from app.services.embedding_service import store_anomaly
    from app.redis_client import redis_client
    from data.simulator import gas_status

    eq_id = reading.get("equipment_id", "unknown")
    result = detect_anomaly(reading)

    # Metan (İSG) değerlendirmesi — mutlak eşik, ML'den bağımsız
    gas_val = float(reading.get("gas", 0.0))
    gas_eval = gas_status(gas_val)
    gas_alarm = gas_eval["seviye"] != "NORMAL"

    async with AsyncSessionLocal() as db:
        db.add(SensorReading(
            equipment_id   = eq_id,
            equipment_type = reading.get("equipment_type"),
            temperature    = reading["temperature"],
            vibration      = reading["vibration"],
            pressure       = reading["pressure"],
            current        = reading["current"],
            speed          = reading["speed"],
            gas            = gas_val,
            is_anomaly     = result["is_anomaly"],
            anomaly_score  = result["anomaly_score"],
        ))

        if result["is_anomaly"]:
            db.add(AnomalyLog(
                equipment_id   = eq_id,
                equipment_type = reading.get("equipment_type"),
                anomaly_score  = result["anomaly_score"],
                description    = result["description"],
            ))

            payload = {
                "equipment_id":  eq_id,
                "anomaly_score": result["anomaly_score"],
                "description":   result["description"],
                "temperature":   reading["temperature"],
                "time":          datetime.now(timezone.utc).isoformat(),
            }
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, notify, payload)
            loop.run_in_executor(
                None, store_anomaly,
                result["description"] or "anomali",
                {"equipment_id": eq_id, "score": result["anomaly_score"]},
            )

        # İSG metan alarmı — anomaliden bağımsız güvenlik kaydı + bildirim
        if gas_alarm:
            db.add(AnomalyLog(
                equipment_id   = eq_id,
                equipment_type = reading.get("equipment_type"),
                anomaly_score  = 1.0,
                description    = f"İSG METAN {gas_eval['seviye']}: {gas_eval['mesaj']}",
            ))
            asyncio.get_event_loop().run_in_executor(None, notify, {
                "equipment_id":  eq_id,
                "tip":           "isg_metan",
                "seviye":        gas_eval["seviye"],
                "gas":           gas_val,
                "description":   gas_eval["mesaj"],
                "time":          datetime.now(timezone.utc).isoformat(),
            })

        await db.commit()

    # Redis: canlı dashboard için son durum (60 sn TTL)
    await redis_client.setex(
        f"latest:{eq_id}", 60,
        json.dumps({**reading, **result, "gas_status": gas_eval}),
    )


def _on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        client.subscribe(TOPIC, qos=1)
        print(f"MQTT subscriber bağlandı → {MQTT_HOST}:{MQTT_PORT}  (abone: {TOPIC})")
    else:
        print(f"MQTT bağlantı hatası: {reason_code}")


def _on_message(client, userdata, msg):
    """paho thread'inde çalışır → işi ana event loop'a devret."""
    try:
        reading = json.loads(msg.payload.decode())
    except Exception:
        return
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(_handle_reading(reading), _loop)


def start(loop: asyncio.AbstractEventLoop):
    """FastAPI startup'ta çağrılır. Subscriber'ı arka thread'de başlatır."""
    global _client, _loop
    _loop = loop
    _client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="maden-subscriber",
    )
    _client.on_connect = _on_connect
    _client.on_message = _on_message
    _client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    _client.loop_start()


def stop():
    global _client
    if _client:
        _client.loop_stop()
        _client.disconnect()
        _client = None


def status() -> dict:
    """Subscriber bağlantı durumu (dashboard için)."""
    connected = bool(_client and _client.is_connected())
    return {
        "baglanti":  "aktif" if connected else "kapalı",
        "broker":    f"{MQTT_HOST}:{MQTT_PORT}",
        "topic":     TOPIC,
        "protokol":  "MQTT 3.1.1 (Eclipse Mosquitto)",
    }
