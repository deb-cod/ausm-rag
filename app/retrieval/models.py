from typing import Any

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    concept_id: str
    content: str
    title: str
    heading: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    source_file: str
    source_sha256: str
    okf_type: str
    status: str | None = None
    trust_tier: str = "unverified"
    stale_after: str | None = None
    is_stale: bool = False
    score: float
    channels: list[str] = Field(default_factory=list)
    channel_scores: dict[str, float] = Field(default_factory=dict)
    citation: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RetrievalBatch(BaseModel):
    results: list[SearchResult]
    dense_candidates: int
    sparse_candidates: int
