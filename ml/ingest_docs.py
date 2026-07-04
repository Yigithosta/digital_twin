"""
Teknik Doküman Vektörleştirme (İP-4: servis manuelleri → Qdrant)
-----------------------------------------------------------------
Sandvik PDF'lerinden metin çıkarır, parçalara (chunk) ayırır, embed eder ve
'sandvik_knowledge' koleksiyonuna ekler. Küratörlü 12 blokluk bilgi tabanının
üzerine gerçek doküman içeriği ekler.

Çalıştırma:  python3 ml/ingest_docs.py [pdf_yolu ...]
Varsayılan:  ~/Downloads içindeki bilinen Sandvik PDF'leri
"""

import sys, os, re, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pdfplumber
from qdrant_client.models import PointStruct
from app.services.rag_service import _get_encoder, _get_qdrant, _ensure_collection, COLLECTION

DEFAULT_PDFS = [
    "~/Downloads/lh517-specification-sheet-english.pdf",
    "~/Downloads/716133205-4-LHD-517.pdf",
]
CHUNK_CHARS = 550
MIN_CHARS   = 120   # anlamsız kısa parçaları at


def extract_chunks(path: str):
    """PDF sayfalarını okuyup temiz metin parçaları üretir."""
    chunks = []
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            text = (page.extract_text() or "")
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) < MIN_CHARS:
                continue
            for i in range(0, len(text), CHUNK_CHARS):
                part = text[i:i + CHUNK_CHARS].strip()
                if len(part) >= MIN_CHARS:
                    chunks.append((pno, part))
    return chunks


def main(paths):
    _ensure_collection()
    enc, q = _get_encoder(), _get_qdrant()
    total = 0
    for raw in paths:
        path = os.path.expanduser(raw)
        if not os.path.exists(path):
            print(f"  atlandı (yok): {path}")
            continue
        name = os.path.basename(path)
        chunks = extract_chunks(path)
        points = []
        for pno, text in chunks:
            vec = enc.encode(text).tolist()
            points.append(PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{name}:{pno}:{text[:40]}")),
                vector=vec,
                payload={
                    "id":           f"doc-{name}-p{pno}",
                    "category":     "Servis Dokümanı",
                    "title":        f"{name} — sayfa {pno}",
                    "content":      text,
                    "part_numbers": [],
                    "failure_mode": "dokuman",
                },
            ))
        if points:
            q.upsert(collection_name=COLLECTION, points=points)
        print(f"  {name}: {len(chunks)} parça vektörize edildi")
        total += len(chunks)
    info = q.get_collection(COLLECTION)
    print(f"\nToplam eklenen parça: {total} · Koleksiyon boyutu: {info.points_count}")


if __name__ == "__main__":
    args = sys.argv[1:] or DEFAULT_PDFS
    main(args)
