from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.sensor import AnomalyLog
from app.schemas.sensor import AnomalyLogOut
from app.services import embedding_service

router = APIRouter(prefix="/anomalies", tags=["Anomaliler"])


@router.get("/", response_model=List[AnomalyLogOut])
async def list_anomalies(
    hours: int = Query(default=24, ge=1, le=168),
    equipment_id: Optional[str] = None,
    resolved: Optional[bool] = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = select(AnomalyLog).where(AnomalyLog.time >= since)
    if equipment_id:
        q = q.where(AnomalyLog.equipment_id == equipment_id)
    if resolved is not None:
        q = q.where(AnomalyLog.resolved == resolved)
    result = await db.execute(q.order_by(desc(AnomalyLog.time)).limit(limit))
    return result.scalars().all()


@router.post("/{anomaly_id}/resolve")
async def resolve_anomaly(anomaly_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        update(AnomalyLog).where(AnomalyLog.id == anomaly_id).values(resolved=True)
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Kayıt bulunamadı")
    return {"status": "çözüldü", "id": anomaly_id}


@router.post("/resolve-all")
async def resolve_all(equipment_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Açık alarmların tümünü (isteğe bağlı tek ekipman için) çözüldü işaretle."""
    q = update(AnomalyLog).where(AnomalyLog.resolved.is_(False))
    if equipment_id:
        q = q.where(AnomalyLog.equipment_id == equipment_id)
    result = await db.execute(q.values(resolved=True))
    await db.commit()
    return {"status": "çözüldü", "adet": result.rowcount}


@router.get("/similar")
def find_similar(description: str, limit: int = Query(default=5, ge=1, le=20)):
    """Qdrant'ta anlamca benzer geçmiş arıza kayıtları."""
    try:
        return embedding_service.search_similar(description, limit=limit)
    except Exception:
        raise HTTPException(503, "Vektör veritabanına ulaşılamıyor")
