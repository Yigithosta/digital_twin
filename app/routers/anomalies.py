from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update
from typing import List
from datetime import datetime, timedelta

from app.database import get_db
from app.models.sensor import AnomalyLog
from app.schemas.sensor import AnomalyLogOut
from app.services import embedding_service

router = APIRouter(prefix="/anomalies", tags=["Anomaliler"])


@router.get("/", response_model=List[AnomalyLogOut])
async def list_anomalies(
    hours: int = Query(default=24, ge=1, le=168),
    equipment_id: str = None,
    db: AsyncSession = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(hours=hours)
    q = select(AnomalyLog).where(AnomalyLog.time >= since).order_by(desc(AnomalyLog.time))
    if equipment_id:
        q = q.where(AnomalyLog.equipment_id == equipment_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/{anomaly_id}/resolve")
async def resolve_anomaly(anomaly_id: int, db: AsyncSession = Depends(get_db)):
    await db.execute(
        update(AnomalyLog).where(AnomalyLog.id == anomaly_id).values(resolved=True)
    )
    await db.commit()
    return {"status": "çözüldü", "id": anomaly_id}


@router.get("/similar")
async def find_similar(description: str, limit: int = 5):
    results = embedding_service.search_similar(description, limit=limit)
    return results
