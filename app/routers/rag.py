"""RAG (Teknik Asistan): Sandvik LH517 dokümantasyonu üzerinde semantik arama."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import rag_service

router = APIRouter(prefix="/rag", tags=["RAG Teknik Asistan"])


class SoruRequest(BaseModel):
    soru: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=3, ge=1, le=10)


def _unavailable(exc: Exception):
    raise HTTPException(503, "Bilgi tabanına (Qdrant) ulaşılamıyor") from exc


@router.get("/status")
def status():
    """Bilgi tabanı durumu."""
    try:
        info = rag_service._get_qdrant().get_collection(rag_service.COLLECTION)
    except Exception:
        return {"durum": "kullanılamıyor", "koleksiyon": rag_service.COLLECTION}
    return {
        "durum":        "aktif",
        "koleksiyon":   rag_service.COLLECTION,
        "toplam_belge": info.points_count,
        "model":        "text-embedding-3-small" if rag_service.EMBEDDING_BACKEND == "openai"
                        else "all-MiniLM-L6-v2",
    }


@router.post("/indeks")
def indeks_olustur():
    """Küratörlü bilgi tabanını Qdrant'a yükle."""
    try:
        rag_service.index_knowledge()
    except Exception as exc:
        _unavailable(exc)
    return {"mesaj": "Bilgi tabanı yüklendi."}


@router.post("/sor")
def sor(req: SoruRequest):
    """Teknik soru sor; dokümantasyondan en ilgili bölümleri getir."""
    try:
        results = rag_service.query(req.soru, limit=req.limit)
    except Exception as exc:
        _unavailable(exc)
    return {
        "soru":     req.soru,
        "sonuclar": results,
        "kaynak":   "Sandvik LH517 Teknik Dokümantasyon",
    }


@router.get("/anomali-asistan")
def anomali_asistan(ekipman: str, aciklama: str):
    """Anomali açıklamasına göre ilgili bakım bilgisini getir."""
    try:
        return rag_service.query_by_anomaly(ekipman, aciklama)
    except Exception as exc:
        _unavailable(exc)
