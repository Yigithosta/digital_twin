"""
PDF Raporlama endpoint'i (İP-5).
n8n workflow'u ve dashboard bu endpoint'ten raporu indirir.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.models.sensor import SensorReading, AnomalyLog
from app.services.report_generator import build_anomaly_report

router = APIRouter(prefix="/report", tags=["Raporlama (PDF)"])

EQUIPMENT_IDS = ["conveyor_01", "pump_01", "crusher_01"]


@router.get("/anomali-pdf")
async def anomali_pdf(db: AsyncSession = Depends(get_db)):
    """Son 24 saatin anomali + RUL özet raporunu PDF olarak döner."""
    now = datetime.now(timezone.utc)

    total = await db.scalar(select(func.count()).select_from(SensorReading))
    a24 = await db.scalar(select(func.count()).select_from(AnomalyLog)
                          .where(AnomalyLog.time >= now - timedelta(hours=24)))
    a1 = await db.scalar(select(func.count()).select_from(AnomalyLog)
                         .where(AnomalyLog.time >= now - timedelta(hours=1)))
    summary = {"toplam_okuma": total or 0, "anomali_24h": a24 or 0, "anomali_1h": a1 or 0}

    rows = await db.execute(
        select(AnomalyLog)
        .where(AnomalyLog.time >= now - timedelta(hours=24))
        .order_by(desc(AnomalyLog.time)).limit(40)
    )
    anomalies = [{
        "time": l.time.isoformat(),
        "equipment_id": l.equipment_id,
        "anomaly_score": float(l.anomaly_score or 0),
        "description": l.description,
    } for l in rows.scalars().all()]

    # RUL: her ekipman için canlı LSTM tahmini (veri yetersizse atla)
    rul_rows = []
    from app.routers.predict import _recent_sequence
    from app.services.lstm_predictor import predict_rul
    for eq in EQUIPMENT_IDS:
        try:
            seq = await _recent_sequence(eq, db)
            r = predict_rul(seq, eq)
            rul_rows.append({"equipment_id": eq, "rul_saat": r.get("rul_saat"),
                             "saglik_yuzde": r.get("saglik_yuzde"), "durum": r.get("durum")})
        except Exception:
            rul_rows.append({"equipment_id": eq, "rul_saat": "-", "saglik_yuzde": "-", "durum": "-"})

    pdf_bytes = build_anomaly_report(summary, anomalies, rul_rows)
    fname = f"anomali_raporu_{now.strftime('%Y%m%d_%H%M')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
