import hashlib
import json
from collections.abc import Sequence
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.config import Settings
from app.embeddings.base import EmbeddingProvider
from app.ingestion.chunker import Chunk
from app.retrieval.sparse import LocalSparseEncoder


class IndexingError(RuntimeError):
    pass


class QdrantIndex:
    """Named dense+sparse collection with dynamic dense-vector dimensions."""

    PAYLOAD_INDEXES: dict[str, models.PayloadSchemaType] = {
        "document_id": models.PayloadSchemaType.KEYWORD,
        "concept_id": models.PayloadSchemaType.KEYWORD,
        "okf_type": models.PayloadSchemaType.KEYWORD,
        "tags": models.PayloadSchemaType.KEYWORD,
        "status": models.PayloadSchemaType.KEYWORD,
        "source_sha256": models.PayloadSchemaType.KEYWORD,
        "parent_id": models.PayloadSchemaType.KEYWORD,
    }

    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingProvider,
        client: AsyncQdrantClient | None = None,
    ):
        self.settings = settings
        self.embeddings = embeddings
        self.client = client or AsyncQdrantClient(url=settings.qdrant_url, timeout=30)
        self.sparse = LocalSparseEncoder()

    async def close(self) -> None:
        await self.client.close()

    async def healthy(self) -> bool:
        try:
            await self.client.get_collections()
            return True
        except Exception:
            return False

    async def ensure_collection(self, dimension: int | None = None) -> int:
        if await self.client.collection_exists(self.settings.qdrant_collection):
            info = await self.client.get_collection(self.settings.qdrant_collection)
            vectors = info.config.params.vectors
            dense_config = vectors.get("dense") if isinstance(vectors, dict) else vectors
            existing_size = int(dense_config.size)
            if dimension is not None and existing_size != dimension:
                raise IndexingError(
                    "Embedding dimension changed "
                    f"({existing_size} -> {dimension}); run rebuild-index"
                )
            return existing_size
        if dimension is None:
            probe = await self.embeddings.embed("embedding dimension probe")
            dimension = len(probe)
        await self.client.create_collection(
            collection_name=self.settings.qdrant_collection,
            vectors_config={
                "dense": models.VectorParams(size=dimension, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={
                "sparse": models.SparseVectorParams(
                    index=models.SparseIndexParams(on_disk=False), modifier=models.Modifier.IDF
                )
            },
        )
        for field, schema in self.PAYLOAD_INDEXES.items():
            await self.client.create_payload_index(
                collection_name=self.settings.qdrant_collection,
                field_name=field,
                field_schema=schema,
            )
        return dimension

    async def index_chunks(self, chunks: Sequence[Chunk], batch_size: int = 32) -> None:
        if not chunks:
            return
        for offset in range(0, len(chunks), batch_size):
            batch = chunks[offset : offset + batch_size]
            vectors = await self._cached_embeddings([chunk.content for chunk in batch])
            await self.ensure_collection(len(vectors[0]))
            points = []
            for chunk, vector in zip(batch, vectors, strict=True):
                payload = chunk.model_dump(mode="json")
                payload["title"] = (
                    chunk.heading_path[0] if chunk.heading_path else chunk.source_file
                )
                points.append(
                    models.PointStruct(
                        id=chunk.chunk_id,
                        vector={"dense": vector, "sparse": self.sparse.encode(chunk.content)},
                        payload=payload,
                    )
                )
            await self.client.upsert(
                collection_name=self.settings.qdrant_collection,
                points=points,
                wait=True,
            )

    async def delete_document(self, document_id: str) -> None:
        if not await self.client.collection_exists(self.settings.qdrant_collection):
            return
        await self.client.delete(
            collection_name=self.settings.qdrant_collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id", match=models.MatchValue(value=document_id)
                        )
                    ]
                )
            ),
            wait=True,
        )

    async def recreate_collection(self, dimension: int) -> None:
        if await self.client.collection_exists(self.settings.qdrant_collection):
            await self.client.delete_collection(self.settings.qdrant_collection)
        await self.ensure_collection(dimension)

    async def _cached_embeddings(self, texts: Sequence[str]) -> list[list[float]]:
        cache_dir = self.settings.cache_dir / "embeddings"
        cache_dir.mkdir(parents=True, exist_ok=True)
        results: list[list[float] | None] = [None] * len(texts)
        misses: list[str] = []
        miss_indices: list[int] = []
        for index, text in enumerate(texts):
            digest = hashlib.sha256(
                f"{self.settings.ollama_embedding_model}\0{text}".encode()
            ).hexdigest()
            path = cache_dir / f"{digest}.json"
            if path.exists():
                try:
                    results[index] = [float(value) for value in json.loads(path.read_text())]
                    continue
                except (OSError, ValueError, TypeError):
                    pass
            misses.append(text)
            miss_indices.append(index)
        if misses:
            vectors = await self.embeddings.embed_batch(misses)
            for index, text, vector in zip(miss_indices, misses, vectors, strict=True):
                results[index] = vector
                digest = hashlib.sha256(
                    f"{self.settings.ollama_embedding_model}\0{text}".encode()
                ).hexdigest()
                (cache_dir / f"{digest}.json").write_text(json.dumps(vector))
        return [result for result in results if result is not None]


def payload_from_point(point: Any, score: float, channel: str) -> dict[str, Any]:
    payload = dict(point.payload or {})
    payload.update(score=float(score), channels=[channel])
    return payload
