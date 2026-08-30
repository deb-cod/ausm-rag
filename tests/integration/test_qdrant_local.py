from pathlib import Path

import pytest
from qdrant_client import AsyncQdrantClient

from app.config import Settings
from app.ingestion.chunker import Chunk
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.index import QdrantIndex


class FakeEmbeddings:
    async def embed(self, text: str) -> list[float]:
        return self._one(text)

    async def embed_batch(self, texts) -> list[list[float]]:
        return [self._one(text) for text in texts]

    @staticmethod
    def _one(text: str) -> list[float]:
        lowered = text.casefold()
        return [
            float("authentication" in lowered),
            float("leave" in lowered),
            0.1,
        ]


def chunk(chunk_id: str, document_id: str, content: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        concept_id=f"documents/{document_id}/topic",
        parent_id=None,
        heading="Topic",
        heading_path=["Topic"],
        content=content,
        chunk_index=0,
        source_file=f"{document_id}.md",
        source_type="md",
        tags=["test"],
        okf_type="Reference",
        status="draft",
        source_sha256=document_id,
    )


@pytest.mark.asyncio
async def test_dense_sparse_index_filter_and_hybrid_search(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path,
        qdrant_collection="test_smart_rag",
        dense_top_k=5,
        sparse_top_k=5,
        fused_top_k=5,
    )
    settings.ensure_directories()
    client = AsyncQdrantClient(location=":memory:")
    embeddings = FakeEmbeddings()
    index = QdrantIndex(settings, embeddings, client)  # type: ignore[arg-type]
    try:
        await index.index_chunks(
            [
                chunk(
                    "11111111-1111-1111-1111-111111111111",
                    "doc-auth",
                    "Authentication supports SSO and MFA.",
                ),
                chunk(
                    "22222222-2222-2222-2222-222222222222",
                    "doc-leave",
                    "Annual leave is twenty days.",
                ),
            ]
        )
        retriever = HybridRetriever(settings, embeddings, client)  # type: ignore[arg-type]
        result = await retriever.search("SSO authentication", document_ids=["doc-auth"])
        assert result.dense_candidates == 1
        assert result.sparse_candidates == 1
        assert result.results[0].document_id == "doc-auth"
        assert set(result.results[0].channels) == {"dense", "sparse"}
        await index.delete_document("doc-auth")
        empty = await retriever.search("SSO authentication", document_ids=["doc-auth"])
        assert empty.results == []
    finally:
        await client.close()
