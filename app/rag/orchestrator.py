import time
from collections import defaultdict

import structlog
from sqlalchemy.orm import Session

from app.agents.answer_generator import AnswerGenerator
from app.agents.evidence_checker import EvidenceChecker
from app.agents.planner import RetrievalPlanner
from app.agents.query_analyzer import QueryAnalyzer
from app.database.repository import Repository
from app.rag.state import QueryResponse, RAGState
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.models import RetrievalBatch, SearchResult
from app.retrieval.relationship_expander import RelationshipExpander
from app.retrieval.reranker import AdaptiveReranker

logger = structlog.get_logger(__name__)


class SmartRAGOrchestrator:
    """Readable adaptive state machine: understand, plan, retrieve, assess, retry, answer."""

    def __init__(
        self,
        session: Session,
        analyzer: QueryAnalyzer,
        planner: RetrievalPlanner,
        retriever: HybridRetriever,
        expander: RelationshipExpander,
        reranker: AdaptiveReranker,
        checker: EvidenceChecker,
        generator: AnswerGenerator,
        max_rounds: int,
    ):
        self.session = session
        self.repository = Repository(session)
        self.analyzer = analyzer
        self.planner = planner
        self.retriever = retriever
        self.expander = expander
        self.reranker = reranker
        self.checker = checker
        self.generator = generator
        self.max_rounds = max_rounds

    async def run(self, session_id: str, query: str) -> QueryResponse:
        started = time.perf_counter()
        history_records = self.repository.recent_messages(session_id)
        history = [{"role": item.role, "content": item.content} for item in history_records]
        plan = await self.analyzer.analyze(query, history)
        retrieval_plan = self.planner.build(plan)
        self.repository.add_message(session_id, "user", query)
        record = self.repository.create_query(session_id, plan)
        self.repository.add_query_plan(
            record.id,
            {
                "query_analysis": plan.model_dump(mode="json"),
                "retrieval_plan": retrieval_plan.model_dump(mode="json"),
            },
        )
        if plan.comparison_targets:
            self.repository.record_comparisons(plan.comparison_targets)
        self.session.commit()

        state = RAGState(
            query_id=record.id,
            session_id=session_id,
            plan=plan,
            retrieval_plan=retrieval_plan,
            subqueries=retrieval_plan.queries,
        )
        document_ids = self._resolve_document_filters(plan.document_filters)
        refinement: str | None = None
        for round_number in range(1, self.max_rounds + 1):
            state.retrieval_rounds = round_number
            round_queries = [refinement] if refinement else state.subqueries
            if not round_queries:
                break
            batches: list[RetrievalBatch] = []
            for subquery in round_queries:
                retrieval_started = time.perf_counter()
                batch = await self.retriever.search(subquery, document_ids=document_ids or None)
                duration_ms = (time.perf_counter() - retrieval_started) * 1000
                batches.append(batch)
                self.repository.add_retrieval_run(
                    state.query_id,
                    round_number,
                    subquery,
                    plan.retrieval_strategy,
                    batch.dense_candidates,
                    batch.sparse_candidates,
                    batch.results,
                    duration_ms,
                )
            merged = self._merge_balanced(batches)
            merged = await self.expander.expand(merged)
            state.evidence = await self.reranker.rerank(
                plan.standalone_query, merged, plan.query_type, plan.exact_terms
            )
            state.assessment = await self.checker.assess(plan, state.evidence)
            self.session.commit()
            if state.assessment.sufficient:
                break
            refinement = state.assessment.refinement_query
            if not refinement:
                break

        sufficient = bool(state.assessment and state.assessment.sufficient)
        state.answer = await self.generator.generate(plan, state.evidence, sufficient)
        confidence = state.assessment.confidence if state.assessment else 0.0
        no_answer = not sufficient
        latency_ms = (time.perf_counter() - started) * 1000
        sources = state.evidence if sufficient else []
        for citation, source in enumerate(sources, 1):
            source.citation = citation
        self.repository.finish_query(
            state.query_id, state.answer, confidence, no_answer, latency_ms, sources
        )
        self.repository.add_message(session_id, "assistant", state.answer)
        self.session.commit()
        logger.info(
            "query_complete",
            query_id=state.query_id,
            trace_id=state.query_id,
            session_id=session_id,
            operation="query",
            duration=latency_ms,
            result_count=len(sources),
        )
        return QueryResponse(
            query_id=state.query_id,
            trace_id=state.query_id,
            session_id=session_id,
            answer=state.answer,
            query_type=plan.query_type.value,
            standalone_query=plan.standalone_query,
            comparison_targets=plan.comparison_targets,
            confidence=confidence,
            no_answer=no_answer,
            retrieval_rounds=state.retrieval_rounds,
            latency_ms=latency_ms,
            sources=sources,
        )

    def _merge_balanced(self, batches: list[RetrievalBatch]) -> list[SearchResult]:
        if not batches:
            return []
        if len(batches) == 1:
            return batches[0].results
        by_id: dict[str, SearchResult] = {}
        appearances: defaultdict[str, int] = defaultdict(int)
        for batch in batches:
            for rank, result in enumerate(batch.results):
                appearances[result.chunk_id] += 1
                existing = by_id.get(result.chunk_id)
                score = result.score + 1.0 / (60 + rank + 1)
                if existing:
                    existing.score += score
                    existing.channels = list(dict.fromkeys(existing.channels + result.channels))
                else:
                    copy = result.model_copy(deep=True)
                    copy.score = score
                    by_id[result.chunk_id] = copy
        # Cross-subquery evidence receives a modest boost, without letting one target dominate.
        for chunk_id, result in by_id.items():
            result.score *= 1 + 0.1 * (appearances[chunk_id] - 1)
        return sorted(by_id.values(), key=lambda item: item.score, reverse=True)

    def _resolve_document_filters(self, filters: list[str]) -> list[str]:
        if not filters:
            return []
        lowered = [item.casefold() for item in filters]
        return [
            document.id
            for document in self.repository.list_documents()
            if any(term in document.filename.casefold() for term in lowered)
        ]
