from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from dotenv import load_dotenv
import os
import uuid

load_dotenv()

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
        _qdrant = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", 6333)),
        )
        _ensure_collection(_qdrant)
    return _qdrant


def _ensure_collection(client: QdrantClient):
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def store_anomaly(description: str, metadata: dict) -> str:
    encoder = _get_encoder()
    qdrant = _get_qdrant()
    embedding = encoder.encode(description).tolist()
    point_id = str(uuid.uuid4())
    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=[PointStruct(id=point_id, vector=embedding, payload=metadata)],
    )
    return point_id


def search_similar(description: str, limit: int = 5) -> list:
    encoder = _get_encoder()
    qdrant = _get_qdrant()
    embedding = encoder.encode(description).tolist()
    response = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=embedding,
        limit=limit,
    )
    return [{"score": r.score, "payload": r.payload} for r in response.points]
