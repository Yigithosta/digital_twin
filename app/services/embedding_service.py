from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import uuid

from app.config import QDRANT_HOST, QDRANT_PORT

import logging

log = logging.getLogger("qdrant")

COLLECTION_NAME = "anomaly_logs"
VECTOR_SIZE = 384

_encoder: SentenceTransformer = None
_qdrant: QdrantClient = None


def _get_encoder() -> SentenceTransformer:
    global _encoder
    if _encoder is None:
        _encoder = SentenceTransformer("all-MiniLM-L6-v2")
    return _encoder


def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=5)
        _ensure_collection(_qdrant)
    return _qdrant


def resolve_collection(client: QdrantClient, name: str, size: int) -> str:
    """
    Koleksiyonu yoksa oluşturur ve kullanılacak adı döner. Aynı adla farklı
    boyutta (başka bir embedding modeliyle oluşturulmuş) bir koleksiyon varsa
    ona dokunmaz; boyut ekli ayrı bir koleksiyon kullanır.
    """
    existing = {c.name for c in client.get_collections().collections}
    if name in existing:
        current = client.get_collection(name).config.params.vectors.size
        if current == size:
            return name
        log.warning("'%s' koleksiyonu %s boyutlu; %s boyut için '%s_%s' kullanılıyor.",
                    name, current, size, name, size)
        name = f"{name}_{size}"
        if name in existing:
            return name
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=size, distance=Distance.COSINE),
    )
    return name


def _ensure_collection(client: QdrantClient):
    global COLLECTION_NAME
    COLLECTION_NAME = resolve_collection(client, COLLECTION_NAME, VECTOR_SIZE)


def store_anomaly(description: str, metadata: dict) -> str:
    encoder = _get_encoder()
    qdrant = _get_qdrant()
    embedding = encoder.encode(description, show_progress_bar=False).tolist()
    point_id = str(uuid.uuid4())
    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=[PointStruct(id=point_id, vector=embedding, payload=metadata)],
    )
    return point_id


def search_similar(description: str, limit: int = 5) -> list:
    encoder = _get_encoder()
    qdrant = _get_qdrant()
    embedding = encoder.encode(description, show_progress_bar=False).tolist()
    response = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=embedding,
        limit=limit,
    )
    return [{"score": r.score, "payload": r.payload} for r in response.points]
