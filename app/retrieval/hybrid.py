from collections import defaultdict

from qdrant_client import AsyncQdrantClient

from app.config import Settings
from app.embeddings.base import EmbeddingProvider
from app.retrieval.filters import build_filter
from app.retrieval.models import RetrievalBatch, SearchResult
from app.retrieval.sparse import LocalSparseEncoder
from app.utils.text import parse_locator_query


class HybridRetriever:
    """Independent dense and lexical searches fused with reciprocal rank fusion."""

    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingProvider,
        client: AsyncQdrantClient,
    ):
        self.settings = settings
        self.embeddings = embeddings
        self.client = client
        self.sparse = LocalSparseEncoder()

    async def search(
        self,
        query: str,
        *,
        document_ids: list[str] | None = None,
        concept_ids: list[str] | None = None,
    ) -> RetrievalBatch:
        query_filter = build_filter(document_ids=document_ids, concept_ids=concept_ids)
        dense_vector = await self.embeddings.embed(query)
        dense_response = await self.client.query_points(
            collection_name=self.settings.qdrant_collection,
            query=dense_vector,
            using="dense",
            query_filter=query_filter,
            limit=self.settings.dense_top_k,
            with_payload=True,
        )
        sparse_query = query
        locator = parse_locator_query(query)
        if locator:
            _kind, target = locator
            # PDF extraction often joins heading words. The compact form lets a query such as
            # "Third Generation Systems" match indexed text such as "ThirdGenerationSystems".
            compact_target = "".join(character for character in target if character.isalnum())
            if compact_target.casefold() != target.casefold():
                sparse_query = f"{query} {compact_target}"
        sparse_response = await self.client.query_points(
            collection_name=self.settings.qdrant_collection,
            query=self.sparse.encode(sparse_query),
            using="sparse",
            query_filter=query_filter,
            limit=self.settings.sparse_top_k,
            with_payload=True,
        )
        dense = dense_response.points
        sparse = sparse_response.points
        fused_scores: dict[str, float] = defaultdict(float)
        channels: dict[str, list[str]] = defaultdict(list)
        channel_scores: dict[str, dict[str, float]] = defaultdict(dict)
        points = {}
        for channel, candidates in (("dense", dense), ("sparse", sparse)):
            for rank, point in enumerate(candidates, 1):
                point_id = str(point.id)
                fused_scores[point_id] += 1.0 / (60 + rank)
                channels[point_id].append(channel)
                channel_scores[point_id][channel] = float(point.score)
                points[point_id] = point
        ordered = sorted(fused_scores, key=fused_scores.get, reverse=True)[
            : self.settings.fused_top_k
        ]
        max_score = max((fused_scores[item] for item in ordered), default=1.0)
        results = []
        for point_id in ordered:
            point = points[point_id]
            payload = dict(point.payload or {})
            try:
                result = SearchResult(
                    **payload,
                    score=fused_scores[point_id] / max_score,
                    channels=channels[point_id],
                    channel_scores=channel_scores[point_id],
                    payload=payload,
                )
            except Exception:
                continue
            results.append(result)
        return RetrievalBatch(
            results=results,
            dense_candidates=len(dense),
            sparse_candidates=len(sparse),
        )
