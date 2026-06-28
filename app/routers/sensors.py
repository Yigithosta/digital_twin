from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List
from datetime import datetime, timedelta, timezone
import json
import asyncio

from app.database import get_db
from app.models.sensor import SensorReading, AnomalyLog
from app.schemas.sensor import SensorReadingCreate, SensorReadingOut
from app.services.anomaly_detector import detect as detect_anomaly
from app.redis_client import redis_client
from data.simulator import generate_reading

router = APIRouter(prefix="/sensors", tags=["Sensörler"])


def _save_to_qdrant(description: str, metadata: dict):
    try:
        from app.services.embedding_service import store_anomaly
        store_anomaly(description, metadata)
    except Exception:
        pass


def _notify_n8n(payload: dict):
    try:
        from app.services.n8n_notifier import notify
        notify(payload)
    except Exception:
        pass


@router.post("/reading", response_model=SensorReadingOut)
async def add_reading(
    data: SensorReadingCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    from data.simulator import gas_status

    result   = detect_anomaly(data.model_dump())
    gas_eval = gas_status(float(data.gas or 0.0))

    record = SensorReading(
        **data.model_dump(),
        is_anomaly=result["is_anomaly"],
        anomaly_score=result["anomaly_score"],
    )
    db.add(record)

    if result["is_anomaly"]:
        log = AnomalyLog(
            equipment_id=data.equipment_id,
            equipment_type=data.equipment_type,
            anomaly_score=result["anomaly_score"],
            description=result["description"],
        )
        db.add(log)

        metadata = {
            "equipment_id":   data.equipment_id,
            "equipment_type": data.equipment_type,
            "anomaly_score":  result["anomaly_score"],
            "temperature":    data.temperature,
            "vibration":      data.vibration,
            "time":           datetime.now(timezone.utc).isoformat(),
        }
        background_tasks.add_task(_save_to_qdrant, result["description"], metadata)
        background_tasks.add_task(_notify_n8n, {**metadata, "description": result["description"]})

    # İSG metan alarmı (mutlak eşik)
    if gas_eval["seviye"] != "NORMAL":
        db.add(AnomalyLog(
            equipment_id=data.equipment_id,
            equipment_type=data.equipment_type,
            anomaly_score=1.0,
            description=f"İSG METAN {gas_eval['seviye']}: {gas_eval['mesaj']}",
        ))
        background_tasks.add_task(_notify_n8n, {
            "equipment_id": data.equipment_id,
            "tip":          "isg_metan",
            "seviye":       gas_eval["seviye"],
            "gas":          data.gas,
            "description":  gas_eval["mesaj"],
            "time":         datetime.now(timezone.utc).isoformat(),
        })

    await db.commit()
    await db.refresh(record)

    await redis_client.setex(
        f"latest:{data.equipment_id}",
        60,
        json.dumps({**data.model_dump(), **result, "gas_status": gas_eval}),
    )

    return record


@router.get("/latest/{equipment_id}")
async def get_latest(equipment_id: str):
    cached = await redis_client.get(f"latest:{equipment_id}")
    if cached:
        return json.loads(cached)
    return {"detail": "Veri bulunamadı"}


@router.get("/history/{equipment_id}", response_model=List[SensorReadingOut])
async def get_history(
    equipment_id: str,
    hours: int = Query(default=1, ge=1, le=72),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(SensorReading)
        .where(SensorReading.equipment_id == equipment_id)
        .where(SensorReading.time >= since)
        .order_by(desc(SensorReading.time))
        .limit(500)
    )
    return result.scalars().all()


@router.post("/simulate/{equipment_id}", response_model=SensorReadingOut)
async def simulate_reading(
    equipment_id: str,
    force_anomaly: bool = False,
    force_gas: bool = False,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
):
    reading = generate_reading(equipment_id, force_anomaly=force_anomaly, force_gas=force_gas)
    schema  = SensorReadingCreate(**reading)
    return await add_reading(schema, background_tasks, db)
