from pydantic import BaseModel, Field

from app.llm.schemas import QueryPlan, RetrievalPlan, SufficiencyAssessment
from app.retrieval.models import SearchResult


class RAGState(BaseModel):
    query_id: str
    session_id: str
    plan: QueryPlan
    retrieval_plan: RetrievalPlan
    subqueries: list[str] = Field(default_factory=list)
    evidence: list[SearchResult] = Field(default_factory=list)
    assessment: SufficiencyAssessment | None = None
    retrieval_rounds: int = 0
    answer: str = ""


class QueryResponse(BaseModel):
    query_id: str
    trace_id: str
    session_id: str
    answer: str
    query_type: str
    standalone_query: str
    comparison_targets: list[str]
    confidence: float
    no_answer: bool
    retrieval_rounds: int
    latency_ms: float
    sources: list[SearchResult]
