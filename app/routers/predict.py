"""LSTM kestirim uç noktaları: kısa vadeli sensör tahmini ve Kalan Faydalı Ömür."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SIMULATOR_INTERVAL
from app.database import get_db
from app.models.sensor import SensorReading
from app.services.lstm_predictor import SEQ_LEN, predict, predict_rul
from data.simulator import EQUIPMENT_PROFILES, FEATURES

router = APIRouter(prefix="/predict", tags=["Tahmin (LSTM)"])


def _check(equipment_id: str):
    if equipment_id not in EQUIPMENT_PROFILES:
        raise HTTPException(404, f"Bilinmeyen ekipman: {equipment_id}")


async def recent_sequence(equipment_id: str, db: AsyncSession):
    result = await db.execute(
        select(SensorReading)
        .where(SensorReading.equipment_id == equipment_id)
        .order_by(desc(SensorReading.time))
        .limit(SEQ_LEN)
    )
    readings = result.scalars().all()
    if len(readings) < SEQ_LEN:
        raise HTTPException(409, f"En az {SEQ_LEN} ölçüm gerekli, mevcut: {len(readings)}")
    return [[getattr(r, k) for k in FEATURES] for r in reversed(readings)]


@router.get("/{equipment_id}")
async def predict_next(
    equipment_id: str,
    steps: int = Query(default=6, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """Son okumalardan sonraki `steps` adımın sensör tahmini."""
    _check(equipment_id)
    sequence = await recent_sequence(equipment_id, db)
    return {
        "equipment_id": equipment_id,
        "adim_saniye": SIMULATOR_INTERVAL,
        "tahmin": predict(sequence, equipment_id, steps=steps),
    }


@router.get("/rul/{equipment_id}")
async def predict_remaining_life(
    equipment_id: str,
    senaryo: str = Query(default="normal", pattern="^(normal|degradasyon)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Kalan Faydalı Ömür (RUL) tahmini.
    - senaryo=normal: canlı verinin son okumalarıyla
    - senaryo=degradasyon: ilerleyen bir arıza senaryosu (demo; gerçek RUL ile kıyaslanır)
    """
    _check(equipment_id)
    if senaryo == "degradasyon":
        from data.simulator import generate_degradation_run
        import random
        run = generate_degradation_run(equipment_id, steps=120)
        end = random.randint(70, 112)        # arızaya 4–25 saat kala bir an
        window = run.iloc[end - SEQ_LEN:end]
        result = predict_rul(window[FEATURES].values.tolist(), equipment_id)
        result["senaryo"]    = "degradasyon"
        result["gercek_rul"] = round(float(window["rul_hours"].iloc[-1]), 1)
        result["ariza_modu"] = run["mode"].iloc[0]
        return result

    sequence = await recent_sequence(equipment_id, db)
    result = predict_rul(sequence, equipment_id)
    result["senaryo"] = "canlı"
    return result
