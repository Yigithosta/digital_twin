"""Ortam değişkenlerinden okunan merkezi ayarlar ve ekipman kaydı."""

import os
from dotenv import load_dotenv

from data.simulator import EQUIPMENT_PROFILES, operating_limits

load_dotenv()


def _flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "digital_twin")
DATABASE_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = "maden/+/sensor"

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/anomali-alarm")

# Dahili saha simülatörü. Gerçek sahada kapatılır; veri MQTT'ye gateway'den gelir.
SIMULATOR_ENABLED = _flag("SIMULATOR_ENABLED")
SIMULATOR_INTERVAL = float(os.getenv("SIMULATOR_INTERVAL", 5))

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]

# ── Ekipman kaydı ────────────────────────────────────────────────────────────
_DISPLAY = {
    "conveyor_01": {"name": "Konveyör Bandı", "zone": "Nakliye Ana Galerisi", "speed_unit": "m/s"},
    "pump_01":     {"name": "Pompa Ünitesi",  "zone": "Üretim Ayağı (Kuzey)", "speed_unit": "rpm"},
    "crusher_01":  {"name": "Kırıcı",         "zone": "Üretim Ayağı (Güney)", "speed_unit": "rpm"},
}

EQUIPMENT_IDS = list(EQUIPMENT_PROFILES.keys())


def equipment_catalog() -> list:
    """Arayüzün ihtiyaç duyduğu ekipman tanımları: ad, bölge, birimler, sınırlar."""
    catalog = []
    for eq_id, profile in EQUIPMENT_PROFILES.items():
        meta = _DISPLAY.get(eq_id, {"name": eq_id, "zone": "—", "speed_unit": ""})
        catalog.append({
            "id": eq_id,
            "type": profile["type"],
            "name": meta["name"],
            "zone": meta["zone"],
            "units": {"temperature": "°C", "vibration": "mm/s", "pressure": "bar",
                      "current": "A", "speed": meta["speed_unit"], "gas": "% CH₄"},
            "limits": operating_limits(eq_id),
        })
    return catalog
