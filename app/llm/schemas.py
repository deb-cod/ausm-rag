from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryType(StrEnum):
    FACTUAL = "factual"
    LOCATOR = "locator"
    DEFINITION = "definition"
    HOW_TO = "how_to"
    COMPARISON = "comparison"
    SUMMARIZATION = "summarization"
    MULTI_HOP = "multi_hop"
    ANALYTICAL = "analytical"
    SYNTHESIS = "synthesis"
    DOCUMENT_SPECIFIC = "document_specific"
    FOLLOW_UP = "follow_up"
    EXPLORATORY = "exploratory"
    NO_RETRIEVAL = "no_retrieval"


class QueryPlan(BaseModel):
    original_query: str
    standalone_query: str
    query_type: QueryType = QueryType.FACTUAL
    entities: list[str] = Field(default_factory=list)
    comparison_targets: list[str] = Field(default_factory=list)
    comparison_dimensions: list[str] = Field(default_factory=list)
    exact_terms: list[str] = Field(default_factory=list)
    temporal_constraints: str | None = None
    document_filters: list[str] = Field(default_factory=list)
    subquestions: list[str] = Field(default_factory=list)
    requires_decomposition: bool = False
    requires_conversation_context: bool = False
    retrieval_strategy: Literal[
        "standard", "locator", "comparison", "multi_hop", "document", "none"
    ] = "standard"


class RetrievalPlan(BaseModel):
    strategy: str
    queries: list[str]
    entity_queries: dict[str, list[str]] = Field(default_factory=dict)
    metadata_filters: dict[str, list[str]] = Field(default_factory=dict)
    use_dense: bool = True
    use_sparse: bool = True
    expand_okf_links: bool = True
    rerank: bool = True


class SufficiencyAssessment(BaseModel):
    sufficient: bool
    confidence: float = Field(ge=0, le=1)
    covered_aspects: list[str] = Field(default_factory=list)
    missing_aspects: list[str] = Field(default_factory=list)
    refinement_query: str | None = None


class RerankItem(BaseModel):
    candidate_id: str
    relevance: float = Field(ge=0, le=1)


class RerankResponse(BaseModel):
    items: list[RerankItem]


class OllamaModelInfo(BaseModel):
    name: str
    model: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class OllamaTags(BaseModel):
    models: list[OllamaModelInfo] = Field(default_factory=list)
