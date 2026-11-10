"""Panel uç noktaları: ekipman kataloğu, özet, canlı durum, zaman serisi, canlı akış."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import EQUIPMENT_IDS, equipment_catalog
from app.database import get_db
from app.models.sensor import AnomalyLog, SensorReading
from app.services import events, mqtt_subscriber
from data.simulator import FEATURES, gas_status

router = APIRouter(tags=["Panel"])

METRICS = {*FEATURES, "gas", "anomaly_score"}


@router.get("/equipment")
async def equipment():
    """Ekipman kataloğu: ad, bölge, birimler ve sensör başına çalışma sınırları."""
    return equipment_catalog()


@router.get("/dashboard/mqtt-status")
async def mqtt_status():
    return mqtt_subscriber.status()


@router.get("/dashboard/summary")
async def summary(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    day, hour = now - timedelta(hours=24), now - timedelta(hours=1)

    async def count(model, *where):
        return await db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    total = await count(SensorReading)
    readings_24h = await count(SensorReading, SensorReading.time >= day)
    flagged_24h = await count(SensorReading, SensorReading.time >= day,
                              SensorReading.is_anomaly.is_(True))
    return {
        "toplam_okuma": total,
        "okuma_24h":    readings_24h,
        "normal_oran":  round(100 * (1 - flagged_24h / readings_24h), 2) if readings_24h else None,
        "anomali_24h":  await count(AnomalyLog, AnomalyLog.time >= day),
        "anomali_1h":   await count(AnomalyLog, AnomalyLog.time >= hour),
        "acik_alarm":   await count(AnomalyLog, AnomalyLog.resolved.is_(False)),
    }


@router.get("/dashboard/latest-all")
async def latest_all(db: AsyncSession = Depends(get_db)):
    """Her ekipmanın son okuması."""
    result = {}
    for eq_id in EQUIPMENT_IDS:
        row = await db.scalar(
            select(SensorReading)
            .where(SensorReading.equipment_id == eq_id)
            .order_by(desc(SensorReading.time))
            .limit(1)
        )
        if row is None:
            continue
        gas = round(row.gas or 0.0, 3)
        result[eq_id] = {
            "equipment_id":  eq_id,
            **{k: round(getattr(row, k), 3) for k in FEATURES},
            "gas":           gas,
            "gas_status":    gas_status(gas),
            "is_anomaly":    row.is_anomaly,
            "anomaly_score": round(row.anomaly_score, 3),
            "time":          row.time.isoformat(),
        }
    return result


@router.get("/dashboard/timeseries/{equipment_id}/{metric}")
async def timeseries(
    equipment_id: str,
    metric: str,
    minutes: int = Query(default=30, ge=1, le=1440),
    points: int = Query(default=240, ge=10, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Grafik için zaman serisi. Uzun aralıklar `points` adet dilime indirgenir."""
    if metric not in METRICS:
        raise HTTPException(400, f"Geçersiz metrik. Geçerli değerler: {sorted(METRICS)}")

    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    rows = (await db.execute(
        select(SensorReading.time, getattr(SensorReading, metric), SensorReading.is_anomaly)
        .where(SensorReading.equipment_id == equipment_id)
        .where(SensorReading.time >= since)
        .order_by(SensorReading.time)
    )).all()

    # Dilim başına ortalama değer; dilimdeki herhangi bir anomali korunur.
    step = max(1, -(-len(rows) // points))
    labels, values, anomalies = [], [], []
    for i in range(0, len(rows), step):
        chunk = rows[i:i + step]
        vals = [float(r[1]) for r in chunk if r[1] is not None]
        labels.append(chunk[-1][0].isoformat())
        values.append(round(sum(vals) / len(vals), 3) if vals else None)
        anomalies.append(any(r[2] for r in chunk))
    return {"labels": labels, "values": values, "anomalies": anomalies}


@router.get("/dashboard/recent-anomalies")
async def recent_anomalies(
    limit: int = Query(default=8, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(select(AnomalyLog).order_by(desc(AnomalyLog.time)).limit(limit))
    return [
        {
            "id":            a.id,
            "time":          a.time.isoformat(),
            "equipment_id":  a.equipment_id,
            "anomaly_score": round(a.anomaly_score or 0.0, 3),
            "description":   a.description,
            "resolved":      a.resolved,
        }
        for a in rows.scalars().all()
    ]


@router.get("/stream")
async def stream(request: Request):
    """Canlı akış (Server-Sent Events): `reading` ve `alarm` olayları."""
    queue = events.subscribe()

    async def generate():
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                data = json.dumps(event["data"], ensure_ascii=False)
                yield f"event: {event['type']}\ndata: {data}\n\n"
        finally:
            events.unsubscribe(queue)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
