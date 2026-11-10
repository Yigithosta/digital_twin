import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app import config
from app.database import engine, init_db
from app.redis_client import redis_client
from app.routers import anomalies, dashboard, predict, rag, report, sensors
from app.services import anomaly_detector, events, mqtt_subscriber

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

VERSION = "2.0.0"


async def _field_simulator():
    """
    Saha sensörlerini taklit eden yayıncı: her turda tüm ekipmanlar için okuma
    üretip MQTT'ye yayınlar; aboneden veri hattına akar.
        simülatör → MQTT (maden/{eq}/sensor) → abone → veri hattı
    Broker'a ulaşılamıyorsa okumalar doğrudan veri hattına verilir.
    """
    from app.services.pipeline import process_reading
    from data.mqtt_publisher import make_client, publish_reading, _sim

    client = make_client()
    client.loop_start()
    await asyncio.sleep(2)
    warned = False
    try:
        while True:
            for eq_id in config.EQUIPMENT_IDS:
                if client.is_connected():
                    publish_reading(client, eq_id)
                    warned = False
                    continue
                if not warned:
                    log.warning("MQTT broker'a ulaşılamıyor; okumalar doğrudan işleniyor.")
                    warned = True
                try:
                    await process_reading(_sim.step(eq_id))
                except Exception as exc:
                    log.warning("Okuma işlenemedi: %s", exc)
            await asyncio.sleep(config.SIMULATOR_INTERVAL)
    finally:
        client.loop_stop()
        client.disconnect()


def _warm_up():
    """Embedding modelini ve bilgi tabanını arka planda hazırlar (ilk istek beklemesin)."""
    from app.services import rag_service
    from app.services.embedding_service import _get_encoder, _get_qdrant
    try:
        _get_encoder()
        _get_qdrant()
        rag_service.index_knowledge()
    except Exception as exc:
        log.warning("RAG bilgi tabanı hazırlanamadı (Qdrant çalışıyor mu?): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    try:
        await init_db()
    except Exception as exc:
        log.error("Veritabanına bağlanılamadı: %s", exc)

    anomaly_detector._load()
    loop.run_in_executor(None, _warm_up)
    mqtt_subscriber.start(loop)
    simulator = asyncio.create_task(_field_simulator()) if config.SIMULATOR_ENABLED else None

    yield

    if simulator:
        simulator.cancel()
    mqtt_subscriber.stop()


app = FastAPI(
    title="Maden Dijital İkiz API",
    description="Maden ekipmanları için gerçek zamanlı izleme, anomali tespiti ve arıza tahmini",
    version=VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (dashboard, sensors, anomalies, predict, rag, report):
    app.include_router(module.router)


@app.get("/api", tags=["Sistem"])
async def info():
    return {"proje": "Maden Dijital İkiz", "versiyon": VERSION, "dokümantasyon": "/docs"}


@app.get("/health", tags=["Sistem"])
async def health():
    """Bileşen bazında sağlık durumu."""
    components = {"mqtt": mqtt_subscriber.status()["baglanti"] == "aktif"}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        components["veritabani"] = True
    except Exception:
        components["veritabani"] = False
    try:
        components["redis"] = bool(await redis_client.ping())
    except Exception:
        components["redis"] = False
    try:
        from app.services.embedding_service import _get_qdrant
        await asyncio.get_running_loop().run_in_executor(None, lambda: _get_qdrant().get_collections())
        components["qdrant"] = True
    except Exception:
        components["qdrant"] = False
    return {
        "status": "ok" if components["veritabani"] else "degraded",
        "versiyon": VERSION,
        "bilesenler": components,
        "canli_abone": events.subscriber_count(),
    }


# Panel (statik dosyalar) — API rotalarından sonra, kökte sunulur.
app.mount("/", StaticFiles(directory="static", html=True), name="panel")
