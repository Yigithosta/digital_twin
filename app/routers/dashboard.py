"""
Demo dashboard için veri endpoint'leri.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, text
from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.models.sensor import SensorReading, AnomalyLog

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/mqtt-status")
async def mqtt_status():
    """MQTT veri giriş katmanının durumu."""
    from app.services import mqtt_subscriber
    return mqtt_subscriber.status()


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db)):
    since_1h = datetime.now(timezone.utc) - timedelta(hours=1)
    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    total = await db.scalar(select(func.count()).select_from(SensorReading))
    anomalies_24h = await db.scalar(
        select(func.count()).select_from(AnomalyLog)
        .where(AnomalyLog.time >= since_24h)
    )
    anomalies_1h = await db.scalar(
        select(func.count()).select_from(AnomalyLog)
        .where(AnomalyLog.time >= since_1h)
    )

    return {
        "toplam_okuma": total,
        "anomali_24h": anomalies_24h,
        "anomali_1h": anomalies_1h,
    }


@router.get("/latest-all")
async def latest_all(db: AsyncSession = Depends(get_db)):
    """Her ekipmanın son okuması."""
    equipment_ids = ["conveyor_01", "pump_01", "crusher_01"]
    result = {}
    for eq_id in equipment_ids:
        row = await db.scalar(
            select(SensorReading)
            .where(SensorReading.equipment_id == eq_id)
            .order_by(desc(SensorReading.time))
            .limit(1)
        )
        if row:
            from data.simulator import gas_status
            gas_val = round(row.gas or 0.0, 3)
            result[eq_id] = {
                "temperature":   round(row.temperature, 2),
                "vibration":     round(row.vibration, 3),
                "pressure":      round(row.pressure, 2),
                "current":       round(row.current, 2),
                "speed":         round(row.speed, 2),
                "gas":           gas_val,
                "gas_status":    gas_status(gas_val),
                "is_anomaly":    row.is_anomaly,
                "anomaly_score": round(row.anomaly_score, 3),
                "time":          row.time.isoformat(),
            }
    return result


@router.get("/timeseries/{equipment_id}/{metric}")
async def timeseries(
    equipment_id: str,
    metric: str,
    minutes: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Grafik için zaman serisi verisi."""
    allowed = {"temperature", "vibration", "pressure", "current", "speed", "gas", "anomaly_score"}
    if metric not in allowed:
        return {"error": "Geçersiz metrik"}

    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    rows = await db.execute(
        select(SensorReading.time, getattr(SensorReading, metric), SensorReading.is_anomaly)
        .where(SensorReading.equipment_id == equipment_id)
        .where(SensorReading.time >= since)
        .order_by(SensorReading.time)
        .limit(200)
    )
    data = rows.all()
    return {
        "labels": [r[0].isoformat() for r in data],
        "values": [round(float(r[1]), 3) for r in data],
        "anomalies": [r[2] for r in data],
    }


@router.get("/recent-anomalies")
async def recent_anomalies(limit: int = 8, db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(AnomalyLog)
        .order_by(desc(AnomalyLog.time))
        .limit(limit)
    )
    logs = rows.scalars().all()
    return [
        {
            "id":            l.id,
            "time":          l.time.isoformat(),
            "equipment_id":  l.equipment_id,
            "anomaly_score": round(l.anomaly_score, 3),
            "description":   l.description,
            "resolved":      l.resolved,
        }
        for l in logs
    ]
