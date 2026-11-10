"""
Sensör okuması işleme hattı.

MQTT abonesi ve REST uç noktaları aynı fonksiyonu kullanır:

    okuma → anomali tespiti (Isolation Forest) + metan eşik kontrolü
          → TimescaleDB kaydı (+ anomali / İSG alarm kaydı)
          → Redis son durum · canlı akış (SSE)
          → alarm varsa: n8n bildirimi + Qdrant'a embedding (arka planda)
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from app.database import AsyncSessionLocal
from app.models.sensor import AnomalyLog, SensorReading
from app.redis_client import redis_client
from app.services import events
from app.services.anomaly_detector import detect as detect_anomaly
from data.simulator import FEATURES, gas_status

log = logging.getLogger("pipeline")

# Metan alarmı seviye yükseldiğinde üretilir; süren bir kaçak her okumada
# yeni kayıt açmaz. Seviye normale dönünce sıfırlanır.
_GAS_RANK = {"NORMAL": 0, "UYARI": 1, "TEHLİKE": 2, "KRİTİK": 3}
_gas_level: dict = {}


def live_payload(reading: dict, result: dict, gas_eval: dict, time: datetime) -> dict:
    """Arayüzün tek bir okuma için beklediği biçim."""
    return {
        "equipment_id":  reading["equipment_id"],
        **{k: round(float(reading[k]), 3) for k in FEATURES},
        "gas":           round(float(reading.get("gas") or 0.0), 3),
        "gas_status":    gas_eval,
        "is_anomaly":    result["is_anomaly"],
        "anomaly_score": round(float(result["anomaly_score"]), 3),
        "time":          time.isoformat(),
    }


def _background(func, *args):
    """Bloklayan yan etkileri (HTTP, embedding) olay döngüsünü tutmadan çalıştırır."""
    def run():
        try:
            func(*args)
        except Exception as exc:   # bildirim hatası veri hattını durdurmamalı
            log.warning("%s başarısız: %s", getattr(func, "__name__", func), exc)
    asyncio.get_running_loop().run_in_executor(None, run)


async def process_reading(reading: dict, db=None) -> SensorReading:
    from app.services.embedding_service import store_anomaly
    from app.services.n8n_notifier import notify

    eq_id = reading["equipment_id"]
    eq_type = reading.get("equipment_type")
    result = detect_anomaly(reading)
    gas_val = float(reading.get("gas") or 0.0)
    gas_eval = gas_status(gas_val)
    now = datetime.now(timezone.utc)

    record = SensorReading(
        time=now,
        equipment_id=eq_id,
        equipment_type=eq_type,
        **{k: float(reading[k]) for k in FEATURES},
        gas=gas_val,
        is_anomaly=result["is_anomaly"],
        anomaly_score=result["anomaly_score"],
    )
    alarms = []
    if result["is_anomaly"]:
        alarms.append(AnomalyLog(
            time=now, equipment_id=eq_id, equipment_type=eq_type,
            anomaly_score=result["anomaly_score"], description=result["description"],
        ))
    gas_rank = _GAS_RANK.get(gas_eval["seviye"], 0)
    gas_escalated = gas_rank > _gas_level.get(eq_id, 0)
    _gas_level[eq_id] = gas_rank
    if gas_escalated:
        alarms.append(AnomalyLog(
            time=now, equipment_id=eq_id, equipment_type=eq_type, anomaly_score=1.0,
            description=f"İSG METAN {gas_eval['seviye']}: {gas_eval['mesaj']}",
        ))

    own_session = db is None
    session = AsyncSessionLocal() if own_session else db
    try:
        session.add(record)
        session.add_all(alarms)
        await session.commit()
        await session.refresh(record)
        for a in alarms:
            await session.refresh(a)
    finally:
        if own_session:
            await session.close()

    payload = live_payload(reading, result, gas_eval, now)
    try:
        await redis_client.setex(f"latest:{eq_id}", 120, json.dumps(payload))
    except Exception as exc:
        log.debug("Redis yazılamadı: %s", exc)

    events.publish({"type": "reading", "data": payload})
    for a in alarms:
        events.publish({"type": "alarm", "data": {
            "id": a.id, "time": now.isoformat(), "equipment_id": eq_id,
            "anomaly_score": round(float(a.anomaly_score), 3),
            "description": a.description, "resolved": False,
        }})

    if result["is_anomaly"]:
        _background(notify, {
            "equipment_id": eq_id, "equipment_type": eq_type,
            "anomaly_score": result["anomaly_score"], "description": result["description"],
            "temperature": reading["temperature"], "vibration": reading["vibration"],
            "time": now.isoformat(),
        })
        _background(store_anomaly, result["description"], {
            "equipment_id": eq_id, "equipment_type": eq_type,
            "anomaly_score": result["anomaly_score"], "time": now.isoformat(),
        })
    if gas_escalated:
        _background(notify, {
            "equipment_id": eq_id, "tip": "isg_metan", "seviye": gas_eval["seviye"],
            "gas": gas_val, "description": gas_eval["mesaj"], "time": now.isoformat(),
        })

    return record
