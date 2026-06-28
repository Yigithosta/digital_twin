"""
RAG (Teknik Asistan) endpoint'leri.
Sandvik LH517 dokümantasyonu üzerinde semantik arama.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.services.rag_service import query, query_by_anomaly, index_knowledge

router = APIRouter(prefix="/rag", tags=["RAG Teknik Asistan"])


class SoruRequest(BaseModel):
    soru: str
    limit: Optional[int] = 3


@router.get("/status")
async def status():
    """Bilgi tabanı durumu."""
    from app.services.rag_service import _get_qdrant, COLLECTION
    q = _get_qdrant()
    try:
        info = q.get_collection(COLLECTION)
        return {
            "durum":         "aktif",
            "koleksiyon":    COLLECTION,
            "toplam_belge":  info.points_count,
            "model":         "all-MiniLM-L6-v2",
        }
    except Exception:
        return {"durum": "koleksiyon bulunamadı"}


@router.post("/indeks")
async def indeks_olustur():
    """Sandvik bilgi tabanını Qdrant'a yükle."""
    index_knowledge()
    return {"mesaj": "Bilgi tabanı başarıyla yüklendi."}


@router.post("/sor")
async def sor(req: SoruRequest):
    """Teknik soru sor, Sandvik dokümantasyonundan yanıt al."""
    results = query(req.soru, limit=req.limit)
    return {
        "soru":    req.soru,
        "sonuclar": results,
        "kaynak":  "Sandvik LH517 / LH410 Teknik Dokümantasyon",
    }


@router.get("/anomali-asistan")
async def anomali_asistan(ekipman: str, aciklama: str):
    """Anomali tespitinde otomatik teknik öneri al."""
    return query_by_anomaly(ekipman, aciklama)
