from qdrant_client import AsyncQdrantClient, models

from app.config import Settings
from app.knowledge.graph import KnowledgeGraph
from app.retrieval.models import SearchResult


class RelationshipExpander:
    def __init__(self, settings: Settings, client: AsyncQdrantClient, graph: KnowledgeGraph):
        self.settings = settings
        self.client = client
        self.graph = graph

    async def expand(self, results: list[SearchResult]) -> list[SearchResult]:
        if not results or self.settings.max_graph_hops == 0:
            return results
        original_ids = {item.chunk_id for item in results}
        related = set(
            self.graph.expand(
                [item.concept_id for item in results], max_hops=self.settings.max_graph_hops
            )
        ) - {item.concept_id for item in results}
        if not related:
            return results
        points, _ = await self.client.scroll(
            collection_name=self.settings.qdrant_collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="concept_id", match=models.MatchAny(any=list(related))
                    )
                ]
            ),
            limit=max(1, self.settings.fused_top_k - len(results)),
            with_payload=True,
            with_vectors=False,
        )
        expanded = list(results)
        for point in points:
            payload = dict(point.payload or {})
            if str(point.id) in original_ids:
                continue
            try:
                expanded.append(
                    SearchResult(
                        **payload,
                        score=0.2,
                        channels=["okf_graph"],
                        payload=payload,
                    )
                )
            except Exception:
                continue
        return expanded
