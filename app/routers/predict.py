"""
LSTM tahmin endpoint'i.
Ekipmanın son SEQ_LEN ölçümüne bakarak bir sonraki değerleri tahmin eder.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.models.sensor import SensorReading
from app.services.lstm_predictor import predict, predict_rul, SEQ_LEN

router = APIRouter(prefix="/predict", tags=["Tahmin (LSTM)"])


async def _recent_sequence(equipment_id: str, db: AsyncSession):
    result = await db.execute(
        select(SensorReading)
        .where(SensorReading.equipment_id == equipment_id)
        .order_by(desc(SensorReading.time))
        .limit(SEQ_LEN)
    )
    readings = result.scalars().all()
    if len(readings) < SEQ_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"En az {SEQ_LEN} ölçüm gerekli, mevcut: {len(readings)}",
        )
    return [
        [r.temperature, r.vibration, r.pressure, r.current, r.speed]
        for r in reversed(readings)
    ]


@router.get("/{equipment_id}")
async def predict_next(equipment_id: str, db: AsyncSession = Depends(get_db)):
    sequence = await _recent_sequence(equipment_id, db)
    return {"equipment_id": equipment_id, "tahmin": predict(sequence)}


@router.get("/rul/{equipment_id}")
async def predict_remaining_life(
    equipment_id: str,
    senaryo: str = "normal",   # normal | degradasyon
    db: AsyncSession = Depends(get_db),
):
    """
    Kalan Faydalı Ömür (RUL) tahmini.
    - senaryo=normal: gerçek son ölçümlerle (sağlıklı durumda yüksek RUL)
    - senaryo=degradasyon: ilerleyen bir arıza senaryosu (jüri demosu)
    """
    if senaryo == "degradasyon":
        from data.simulator import generate_degradation_run
        # arızaya yaklaşmış bir noktadan SEQ_LEN'lik pencere üret
        run = generate_degradation_run(equipment_id, steps=60)
        window = run.iloc[40:40 + SEQ_LEN]   # sona yakın → düşük RUL
        sequence = window[["temperature", "vibration", "pressure",
                           "current", "speed"]].values.tolist()
        gercek_rul = round(float(window["rul_hours"].iloc[-1]), 1)
        result = predict_rul(sequence, equipment_id)
        result["senaryo"]     = "degradasyon (arıza ilerliyor)"
        result["gercek_rul"]  = gercek_rul   # doğrulama için
        result["ariza_modu"]  = run["mode"].iloc[0]
        return result

    sequence = await _recent_sequence(equipment_id, db)
    result = predict_rul(sequence, equipment_id)
    result["senaryo"] = "gerçek zamanlı (canlı veri)"
    return result
