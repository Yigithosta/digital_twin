"""
Veritabanına geçmiş sensör verisi ekler. Docker servisleri çalışırken çalıştırın:
  python data/seed.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from data.simulator import generate_historical
from app.services.anomaly_detector import detect as detect_anomaly
from app.models.sensor import SensorReading, AnomalyLog
from app.database import Base

load_dotenv()

DATABASE_URL = (
    f"postgresql+asyncpg://{os.getenv('POSTGRES_USER', 'postgres')}:"
    f"{os.getenv('POSTGRES_PASSWORD', 'postgres')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5432')}/"
    f"{os.getenv('POSTGRES_DB', 'digital_twin')}"
)


async def seed():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("24 saatlik simüle veri üretiliyor...")
    df = generate_historical(hours=24, interval_seconds=60)
    print(f"{len(df)} satır üretildi, veritabanına yazılıyor...")

    async with Session() as session:
        batch = []
        for _, row in df.iterrows():
            d = row.to_dict()
            result = detect_anomaly(d)
            record = SensorReading(
                time=d["time"],
                equipment_id=d["equipment_id"],
                equipment_type=d["equipment_type"],
                temperature=d["temperature"],
                vibration=d["vibration"],
                pressure=d["pressure"],
                current=d["current"],
                speed=d["speed"],
                is_anomaly=result["is_anomaly"],
                anomaly_score=result["anomaly_score"],
            )
            batch.append(record)
            if result["is_anomaly"]:
                batch.append(AnomalyLog(
                    time=d["time"],
                    equipment_id=d["equipment_id"],
                    equipment_type=d["equipment_type"],
                    anomaly_score=result["anomaly_score"],
                    description=result["description"],
                ))

            if len(batch) >= 200:
                session.add_all(batch)
                await session.commit()
                batch = []

        if batch:
            session.add_all(batch)
            await session.commit()

    print("Seed tamamlandı.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
