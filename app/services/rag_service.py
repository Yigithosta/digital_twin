"""
RAG (Retrieval-Augmented Generation) Servisi
Sandvik LH517 teknik dokümantasyonu üzerinde semantik arama.
"""

import os
import json
from typing import List, Dict
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

COLLECTION = "sandvik_knowledge"
VECTOR_SIZE = 384

_encoder: SentenceTransformer = None
_qdrant: QdrantClient = None
_indexed = False


def _get_encoder():
    global _encoder
    if _encoder is None:
        _encoder = SentenceTransformer("all-MiniLM-L6-v2")
    return _encoder


def _get_qdrant():
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", 6333)),
        )
    return _qdrant


def _ensure_collection():
    q = _get_qdrant()
    existing = [c.name for c in q.get_collections().collections]
    if COLLECTION not in existing:
        q.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


# ── Bilgi Tabanı ──────────────────────────────────────────────────────────────

KNOWLEDGE_BASE = [
    # Motor ve Güç Sistemi
    {
        "id": "lh517-motor-01",
        "category": "Motor Sistemi",
        "title": "LH517 Motor Sıcaklık Limitleri",
        "content": "Sandvik LH517 motor normal çalışma sıcaklığı 70-90°C arasındadır. 95°C üzerinde uyarı alarmı devreye girer. 105°C üzerinde motor otomatik olarak kapatılır. Yüksek sıcaklık tespit edildiğinde: 1) Soğutma sıvısı seviyesini kontrol edin, 2) Radyatör temizliğini yapın, 3) Termostatı test edin.",
        "part_numbers": ["56037200", "56037201"],
        "failure_mode": "aşırı ısınma",
    },
    {
        "id": "lh517-motor-02",
        "category": "Motor Sistemi",
        "title": "LH517 Motor Akım Limitleri",
        "content": "LH517 tahrik motoru nominal akım 185A, maksimum 220A'dir. Sürekli 200A üzeri akım motor sargı arızasına yol açar. Yüksek akım tespitinde: 1) Yük dağılımını kontrol edin, 2) Motor izolasyon direncini ölçün (min. 1MΩ), 3) Fırçaları ve kolektörü kontrol edin. Parça no: 56206419 (SWITCH MAIN), 56024620 (HORN).",
        "part_numbers": ["56206419", "56024620"],
        "failure_mode": "aşırı akım",
    },
    # Titreşim ve Mekanik
    {
        "id": "lh517-vibration-01",
        "category": "Titreşim ve Mekanik",
        "title": "LH517 Titreşim Eşikleri ve Rulman Bakımı",
        "content": "Sandvik LH517 normal titreşim değeri 0-4.5 mm/s RMS'dir. 5-8 mm/s arası erken uyarı bölgesidir; rulman kontrolü önerilir. 8 mm/s üzeri kritik eşik olup makine durdurulmalıdır. Front Frame Assembly (P/N 56204783) bağlantı noktaları kontrol edilmelidir. Liftarms Bushing (P/N 56045500) 500 saat aralıklarla değiştirilmelidir.",
        "part_numbers": ["56204783", "56045500", "56045520"],
        "failure_mode": "aşırı titreşim",
    },
    {
        "id": "lh517-vibration-02",
        "category": "Titreşim ve Mekanik",
        "title": "LH517 Ön Çerçeve ve Bağlantı Parçaları",
        "content": "Front Frame Bushings (P/N 56204784): 140 D9X155 S6/LG 78 ve 155/140-88 standart tiplerdir. Busing aşınması titreşim artışına neden olur. Muayene aralığı 250 çalışma saatidir. Swing Lever Bushings (P/N 56045520) ve Dogbone (P/N 56027788) bağlantı noktaları greslenmeli; 125 saat aralıklarla kontrol edilmelidir.",
        "part_numbers": ["56204784", "56045520", "56027788"],
        "failure_mode": "titreşim, bağlantı aşınması",
    },
    # Hidrolik ve Basınç
    {
        "id": "lh517-hydraulic-01",
        "category": "Hidrolik Sistem",
        "title": "LH517 Hidrolik Basınç Değerleri",
        "content": "LH517 hidrolik sistem çalışma basıncı 250-280 bar arasındadır. Düşük basınç (200 bar altı) pompa aşınması veya filtre tıkanmasına işaret eder. Yüksek basınç (290 bar üzeri) relief valve arızasını gösterir. Rear Tank Assembly (P/N 56037200) hidrolik yağ haznesi kapasitesi 120 litredir. Yağ değişim aralığı 1000 çalışma saatidir.",
        "part_numbers": ["56037200", "56037201", "56028042"],
        "failure_mode": "hidrolik basınç sapması",
    },
    # Elektrik Sistemi
    {
        "id": "lh517-electrical-01",
        "category": "Elektrik Sistemi",
        "title": "LH517 Batarya ve Elektrik Sistemi",
        "content": "LH517 elektrik sistemi 24-48V DC çalışır. Battery (P/N 56020750): asitsiz yedek parça olarak sipariş edilir. Emergency Stop Button (P/N 56013070): YELLOW/RED, IP67 koruma sınıfı, 2 adet. Horn (P/N 56024620): 24-48VDC, 0.8A, 107dB sabit ton. Headlight (P/N 56017520): 1 adet ana far. Elektrik sisteminde arıza tespit edildiğinde önce Emergency Stop butonunu kontrol edin.",
        "part_numbers": ["56020750", "56013070", "56024620", "56017520"],
        "failure_mode": "elektrik arızası",
    },
    {
        "id": "lh517-electrical-02",
        "category": "Elektrik Sistemi",
        "title": "LH517 Uzaktan Kontrol Sistemi",
        "content": "Sandvik LH517 uzaktan kontrol sistemi: Remote Control System Radio (P/N 56045111), Transmitter (P/N 56045293), Interface Remote Control (P/N BG00399273). Uzaktan kontrol arızalarında: 1) Verici pil durumunu kontrol edin, 2) Anten bağlantısını kontrol edin, 3) Frekans çakışmasını kontrol edin. Sistem IP67 koruma sınıfında çalışır.",
        "part_numbers": ["56045111", "56045293", "BG00399273"],
        "failure_mode": "uzaktan kontrol arızası",
    },
    # Yağlama Sistemi
    {
        "id": "lh517-lubrication-01",
        "category": "Yağlama Sistemi",
        "title": "LH517 Merkezi Yağlama Sistemi",
        "content": "Central Lubrication Kit (P/N 56209375): Tüm bağlantı noktalarını otomatik gresleme yapar. Yağlama sıklığı: 8 saatte bir otomatik devreye girer. Manuel kontrol 250 saatte bir yapılmalıdır. Grease nipple tıkanması titreşim ve aşınma artışına neden olur. Covers and Mudguards (P/N 56034355) sökülerek erişim sağlanabilir.",
        "part_numbers": ["56209375", "56034355"],
        "failure_mode": "yağlama yetersizliği",
    },
    # Tartım ve Sensör
    {
        "id": "lh517-sensor-01",
        "category": "Sensör ve Tartım",
        "title": "LH517 Tartım Sistemi ve Sensörler",
        "content": "Weighing System (P/N 56029901): Yük kapasitesi izleme sistemi. Wire Kit (P/N 56015599) ve Balance (P/N 56020567) ile kalibre edilir. Sensor Assembly (P/N 56046804): titreşim ve yük sensörlerini barındırır. Sensör arızası durumunda: 1) Bağlantı kablolarını kontrol edin, 2) Sensör sıfırlama prosedürünü uygulayın, 3) Kalibrasyon değerlerini doğrulayın.",
        "part_numbers": ["56029901", "56015599", "56020567", "56046804"],
        "failure_mode": "sensör arızası, yanlış okuma",
    },
    # Genel Bakım
    {
        "id": "lh517-maintenance-01",
        "category": "Periyodik Bakım",
        "title": "LH517 Bakım Takvimi",
        "content": "Sandvik LH517 bakım aralıkları: 8 saat — yağ seviyeleri, lastik basınç, frenleri kontrol et. 125 saat — filtreler, bağlantı noktaları, gresleme. 250 saat — tüm bushingler, yük sensörü kalibrasyonu, elektrik bağlantıları. 500 saat — motor filtresi değişimi, Liftarm Bushing kontrolü. 1000 saat — hidrolik yağ değişimi, motor incelemesi. Planned maintenance miktarını artırmak downtime'ı %40 azaltır.",
        "part_numbers": [],
        "failure_mode": "genel bakım",
    },
    {
        "id": "lh517-maintenance-02",
        "category": "Periyodik Bakım",
        "title": "LH517 Arıza Tespiti ve Müdahale",
        "content": "LH517 arıza öncelikleri: KIRMIZI (acil durdur) — 105°C üzeri sıcaklık, 220A üzeri akım, 8 mm/s üzeri titreşim. SARI (dikkat) — 95-105°C sıcaklık, 200-220A akım, 5-8 mm/s titreşim. YEŞİL (normal) — tüm değerler normal aralıkta. Müdahale süresi hedefi: KIRMIZI için 15 dakika, SARI için 4 saat içinde bakım planlanmalıdır.",
        "part_numbers": [],
        "failure_mode": "genel arıza müdahalesi",
    },
    {
        "id": "lh517-fire-01",
        "category": "Güvenlik",
        "title": "LH517 Yangın Söndürme ve Güvenlik Sistemi",
        "content": "Fire Extinguishing System (P/N 56205923): Otomatik yangın söndürme sistemi. Motor bölmesindeki sıcaklık sensörü 200°C'yi aştığında otomatik devreye girer. Bakım aralığı 12 aydır. Emergency Stop (P/N 56013070, IP67, YELLOW/RED) her 500 saatte test edilmelidir. Service Railings (P/N 56039605) bakım esnasında mutlaka kullanılmalıdır.",
        "part_numbers": ["56205923", "56013070", "56039605"],
        "failure_mode": "yangın, güvenlik sistemi",
    },
]


def index_knowledge():
    """Bilgi tabanını Qdrant'a yükle."""
    global _indexed
    _ensure_collection()
    q = _get_qdrant()
    enc = _get_encoder()

    # Önce koleksiyonun dolu olup olmadığını kontrol et
    info = q.get_collection(COLLECTION)
    if info.points_count >= len(KNOWLEDGE_BASE):
        _indexed = True
        return

    points = []
    for i, doc in enumerate(KNOWLEDGE_BASE):
        text = f"{doc['title']}: {doc['content']}"
        vector = enc.encode(text).tolist()
        points.append(PointStruct(
            id=i + 1,
            vector=vector,
            payload={
                "id":          doc["id"],
                "category":    doc["category"],
                "title":       doc["title"],
                "content":     doc["content"],
                "part_numbers": doc["part_numbers"],
                "failure_mode": doc["failure_mode"],
            }
        ))

    q.upsert(collection_name=COLLECTION, points=points)
    _indexed = True
    print(f"RAG: {len(points)} bilgi bloğu Qdrant'a yüklendi.")


def query(question: str, limit: int = 3) -> List[Dict]:
    """Soruya en alakalı bilgi bloklarını döndür."""
    if not _indexed:
        index_knowledge()

    enc = _get_encoder()
    q   = _get_qdrant()

    vector  = enc.encode(question).tolist()
    response = q.query_points(
        collection_name=COLLECTION,
        query=vector,
        limit=limit,
        score_threshold=0.3,
    )

    return [
        {
            "score":        round(r.score, 3),
            "category":     r.payload["category"],
            "title":        r.payload["title"],
            "content":      r.payload["content"],
            "part_numbers": r.payload["part_numbers"],
        }
        for r in response.points
    ]


def query_by_anomaly(equipment_type: str, anomaly_description: str) -> Dict:
    """Anomali açıklamasına göre teknik öneri üret."""
    question = f"{equipment_type} {anomaly_description}"
    results  = query(question, limit=2)

    if not results:
        return {
            "soru":    question,
            "sonuclar": [],
            "ozet":    "Bilgi tabanında ilgili kayıt bulunamadı.",
        }

    ozet_parts = []
    for r in results:
        ozet_parts.append(f"[{r['category']}] {r['title']}")

    return {
        "soru":    question,
        "sonuclar": results,
        "ozet":    f"İlgili {len(results)} teknik doküman bulundu: " + " | ".join(ozet_parts),
    }
