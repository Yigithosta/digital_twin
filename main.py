import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.database import init_db
from app.routers import sensors, anomalies, predict
from app.routers import dashboard
from app.routers import rag

EQUIPMENT_IDS = ["conveyor_01", "pump_01", "crusher_01"]
_stream_task  = None


async def _live_stream():
    """
    Saha sensörlerini taklit eden MQTT yayıncısı.
    Her 8 saniyede tüm ekipmanlar için okuma üretir ve MQTT broker'a yayınlar.
    Veriyi tüketip işleyen taraf app.services.mqtt_subscriber'dır.
    Akış:  simülatör → MQTT (maden/{eq}/sensor) → subscriber → DB/Redis/n8n/Qdrant
    """
    from data.mqtt_publisher import make_client, publish_reading
    import random

    # Yayıncı bağlanana kadar kısa bekleme
    await asyncio.sleep(2)
    client = await asyncio.get_event_loop().run_in_executor(None, make_client)
    client.loop_start()
    print("MQTT publisher başladı (canlı yayın).")

    cycle = 0
    try:
        while True:
            await asyncio.sleep(8)
            cycle += 1
            force_eq = random.choice(EQUIPMENT_IDS) if cycle % 15 == 0 else None
            # ~her 25 döngüde bir rastgele ekipmanda metan kaçağı (İSG demo)
            gas_eq = random.choice(EQUIPMENT_IDS) if cycle % 25 == 0 else None
            for eq_id in EQUIPMENT_IDS:
                publish_reading(client, eq_id,
                                force_anomaly=(eq_id == force_eq),
                                force_gas=(eq_id == gas_eq))
    except asyncio.CancelledError:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


async def _setup_n8n():
    """n8n'de anomali alarm workflow'unu otomatik oluşturur."""
    import urllib.request, json, base64, time
    await asyncio.sleep(5)

    workflow = {
        "name": "Anomali Alarm",
        "active": True,
        "nodes": [
            {
                "id": "1", "name": "Webhook", "type": "n8n-nodes-base.webhook",
                "typeVersion": 2, "position": [250, 300],
                "parameters": {
                    "path": "anomali-alarm",
                    "responseMode": "onReceived",
                    "httpMethod": "POST",
                }
            },
            {
                "id": "2", "name": "Log Anomali", "type": "n8n-nodes-base.set",
                "typeVersion": 3, "position": [500, 300],
                "parameters": {
                    "mode": "manual",
                    "assignments": {"assignments": [
                        {"id": "1", "name": "mesaj", "type": "string",
                         "value": "={{ 'ANOMALİ: ' + $json.equipment_id + ' | Skor: ' + $json.anomaly_score + ' | ' + $json.description }}"},
                    ]}
                }
            },
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "Log Anomali", "type": "main", "index": 0}]]}
        },
    }

    try:
        cred = base64.b64encode(b"admin:admin123").decode()
        req  = urllib.request.Request(
            "http://localhost:5678/api/v1/workflows",
            data=json.dumps(workflow).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Basic {cred}",
                     "X-N8N-API-KEY": ""},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        print("n8n workflow oluşturuldu.")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Modelleri ön yükle (ilk istek yavaş olmasın)
    from app.services.anomaly_detector import _load
    from app.services.embedding_service import _get_encoder, _get_qdrant
    from app.services.rag_service import index_knowledge
    from app.services import mqtt_subscriber
    _load()
    await asyncio.get_event_loop().run_in_executor(None, _get_encoder)
    await asyncio.get_event_loop().run_in_executor(None, _get_qdrant)
    await asyncio.get_event_loop().run_in_executor(None, index_knowledge)

    # MQTT abonesini başlat (veri giriş katmanı), ardından yayıncıyı
    mqtt_subscriber.start(asyncio.get_event_loop())

    global _stream_task
    _stream_task = asyncio.create_task(_live_stream())
    yield
    if _stream_task:
        _stream_task.cancel()
    mqtt_subscriber.stop()


app = FastAPI(
    title="Maden Dijital İkiz API",
    description="Maden ekipmanları için anomali tespiti ve tahmin sistemi",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sensors.router)
app.include_router(anomalies.router)
app.include_router(predict.router)
app.include_router(dashboard.router)
app.include_router(rag.router)
from app.routers import report
app.include_router(report.router)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return {
        "proje":         "Maden Dijital İkiz",
        "versiyon":      "1.0.0",
        "durum":         "çalışıyor",
        "dokümantasyon": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
