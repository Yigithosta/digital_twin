"""
MQTT Sensör Abonesi
-------------------
Backend'in veri giriş katmanı. Mosquitto broker'a abone olur ve
`maden/+/sensor` topic'lerinden gelen her mesajı ortak veri hattına
(app.services.pipeline) aktarır.

paho-mqtt kendi thread'inde çalışır; gelen mesaj
asyncio.run_coroutine_threadsafe ile FastAPI'nin olay döngüsüne devredilir.
Broker'a ulaşılamazsa uygulama açılmaya devam eder, paho arka planda
yeniden bağlanmayı dener.
"""

import asyncio
import json
import logging

import paho.mqtt.client as mqtt

from app.config import MQTT_HOST, MQTT_PORT, MQTT_TOPIC

log = logging.getLogger("mqtt")

_client: mqtt.Client = None
_loop: asyncio.AbstractEventLoop = None
_received = 0


def _on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        client.subscribe(MQTT_TOPIC, qos=1)
        log.info("MQTT abonesi bağlandı → %s:%s (%s)", MQTT_HOST, MQTT_PORT, MQTT_TOPIC)
    else:
        log.warning("MQTT bağlantı hatası: %s", reason_code)


def _done(future):
    exc = future.exception()
    if exc:
        log.warning("Okuma işlenemedi: %s", exc)


def _on_message(client, userdata, msg):
    """paho thread'inde çalışır → işi ana olay döngüsüne devret."""
    global _received
    from app.services.pipeline import process_reading
    try:
        reading = json.loads(msg.payload.decode())
        if "equipment_id" not in reading:
            return
    except (ValueError, UnicodeDecodeError):
        return
    _received += 1
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(process_reading(reading), _loop).add_done_callback(_done)


def start(loop: asyncio.AbstractEventLoop):
    """Uygulama açılışında çağrılır; aboneyi arka thread'de başlatır."""
    global _client, _loop
    _loop = loop
    _client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="maden-subscriber",
    )
    _client.on_connect = _on_connect
    _client.on_message = _on_message
    _client.reconnect_delay_set(min_delay=1, max_delay=30)
    _client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
    _client.loop_start()


def stop():
    global _client
    if _client:
        _client.loop_stop()
        _client.disconnect()
        _client = None


def status() -> dict:
    connected = bool(_client and _client.is_connected())
    return {
        "baglanti": "aktif" if connected else "kapalı",
        "broker":   f"{MQTT_HOST}:{MQTT_PORT}",
        "topic":    MQTT_TOPIC,
        "protokol": "MQTT (Eclipse Mosquitto)",
        "alinan_mesaj": _received,
    }
