import json
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.sensor import SensorReading
from app.redis_client import redis_client
from app.schemas.sensor import SensorReadingCreate, SensorReadingOut
from app.services.pipeline import process_reading
from data.simulator import EQUIPMENT_PROFILES, LiveSimulator, resolve_equipment

router = APIRouter(prefix="/sensors", tags=["Sensörler"])

_sim = LiveSimulator()


@router.post("/reading", response_model=SensorReadingOut)
async def add_reading(data: SensorReadingCreate, db: AsyncSession = Depends(get_db)):
    """Yeni okuma al; anomali ve metan kontrolünden geçirip kaydet."""
    if resolve_equipment(data.equipment_id, data.equipment_type) is None:
        raise HTTPException(404, f"Bilinmeyen ekipman: {data.equipment_id}")
    reading = data.model_dump()
    if not reading["equipment_type"]:
        reading["equipment_type"] = EQUIPMENT_PROFILES[data.equipment_id]["type"]
    return await process_reading(reading, db)


@router.get("/latest/{equipment_id}")
async def get_latest(equipment_id: str):
    try:
        cached = await redis_client.get(f"latest:{equipment_id}")
    except Exception:
        raise HTTPException(503, "Redis'e ulaşılamıyor")
    if not cached:
        raise HTTPException(404, "Bu ekipman için güncel veri yok")
    return json.loads(cached)


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
    db: AsyncSession = Depends(get_db),
):
    """Demo: seçilen ekipman için tek bir okuma üret (isteğe bağlı arıza / metan kaçağı)."""
    if equipment_id not in EQUIPMENT_PROFILES:
        raise HTTPException(404, f"Bilinmeyen ekipman: {equipment_id}")
    reading = _sim.step(equipment_id, force_anomaly=force_anomaly, force_gas=force_gas,
                        anomaly_rate=0.0, gas_rate=0.0)
    return await process_reading(reading, db)
