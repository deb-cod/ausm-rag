import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.database.models import (
    AnswerSourceRecord,
    ComparisonEdgeRecord,
    DocumentRecord,
    MessageRecord,
    QueryPlanRecord,
    QueryRecord,
    RetrievalResultRecord,
    RetrievalRunRecord,
    SessionRecord,
)
from app.utils.ids import new_id
from app.utils.text import normalize_question
from app.utils.time import utc_now


class Repository:
    """Small explicit persistence layer; large document content stays outside SQLite."""

    def __init__(self, session: Session):
        self.session = session

    def ensure_session(self, session_id: str) -> SessionRecord:
        record = self.session.get(SessionRecord, session_id)
        if record is None:
            record = SessionRecord(id=session_id)
            self.session.add(record)
        else:
            record.updated_at = utc_now()
        self.session.flush()
        return record

    def add_message(self, session_id: str, role: str, content: str) -> MessageRecord:
        self.ensure_session(session_id)
        record = MessageRecord(id=new_id(), session_id=session_id, role=role, content=content)
        self.session.add(record)
        self.session.flush()
        return record

    def recent_messages(self, session_id: str, limit: int = 8) -> list[MessageRecord]:
        stmt = (
            select(MessageRecord)
            .where(MessageRecord.session_id == session_id)
            .order_by(desc(MessageRecord.created_at))
            .limit(limit)
        )
        return list(reversed(self.session.scalars(stmt).all()))

    def document_by_hash(self, sha256: str) -> DocumentRecord | None:
        return self.session.scalar(select(DocumentRecord).where(DocumentRecord.sha256 == sha256))

    def document_by_filename(self, filename: str) -> DocumentRecord | None:
        return self.session.scalar(
            select(DocumentRecord)
            .where(DocumentRecord.filename == filename)
            .order_by(desc(DocumentRecord.updated_at))
        )

    def list_documents(self) -> list[DocumentRecord]:
        return list(
            self.session.scalars(select(DocumentRecord).order_by(DocumentRecord.filename)).all()
        )

    def create_query(self, session_id: str, plan: Any) -> QueryRecord:
        self.ensure_session(session_id)
        record = QueryRecord(
            id=new_id(),
            session_id=session_id,
            original_query=plan.original_query,
            normalized_query=normalize_question(plan.original_query),
            standalone_query=plan.standalone_query,
            query_type=str(getattr(plan.query_type, "value", plan.query_type)),
            entities_json=json.dumps(plan.entities),
            comparison_targets_json=json.dumps(plan.comparison_targets),
            comparison_dimensions_json=json.dumps(plan.comparison_dimensions),
            subquestions_json=json.dumps(plan.subquestions),
        )
        self.session.add(record)
        self.session.flush()
        return record

    def add_query_plan(self, query_id: str, plan: Any) -> None:
        payload = plan.model_dump(mode="json") if hasattr(plan, "model_dump") else plan
        self.session.add(
            QueryPlanRecord(id=new_id(), query_id=query_id, plan_json=json.dumps(payload))
        )

    def add_retrieval_run(
        self,
        query_id: str,
        round_number: int,
        subquery: str,
        strategy: str,
        dense_candidates: int,
        sparse_candidates: int,
        results: Sequence[Any],
        duration_ms: float,
    ) -> str:
        run_id = new_id()
        run = RetrievalRunRecord(
            id=run_id,
            query_id=query_id,
            round_number=round_number,
            subquery=subquery,
            strategy=strategy,
            dense_candidates=dense_candidates,
            sparse_candidates=sparse_candidates,
            fused_candidates=len(results),
            duration_ms=duration_ms,
        )
        self.session.add(run)
        # There is deliberately no heavy ORM relationship graph. Flush the parent explicitly so
        # SQLite foreign-key enforcement can accept the result rows below.
        self.session.flush()
        for rank, result in enumerate(results, 1):
            self.session.add(
                RetrievalResultRecord(
                    id=new_id(),
                    run_id=run_id,
                    chunk_id=result.chunk_id,
                    document_id=result.document_id,
                    rank=rank,
                    score=result.score,
                    channels_json=json.dumps(result.channels),
                )
            )
        return run_id

    def finish_query(
        self,
        query_id: str,
        answer: str,
        confidence: float,
        no_answer: bool,
        latency_ms: float,
        sources: Sequence[Any],
    ) -> None:
        query = self.session.get(QueryRecord, query_id)
        if query is None:
            raise LookupError(f"Unknown query: {query_id}")
        query.answer = answer
        query.answer_confidence = confidence
        query.no_answer = no_answer
        query.latency_ms = latency_ms
        for number, source in enumerate(sources, 1):
            self.session.add(
                AnswerSourceRecord(
                    id=new_id(),
                    query_id=query_id,
                    chunk_id=source.chunk_id,
                    document_id=source.document_id,
                    citation_number=number,
                    score=source.score,
                )
            )

    def record_comparisons(self, targets: list[str]) -> None:
        unique = list(dict.fromkeys(target.strip() for target in targets if target.strip()))
        for index, first in enumerate(unique):
            for second in unique[index + 1 :]:
                ordered = sorted(((first.casefold(), first), (second.casefold(), second)))
                a_key, a = ordered[0]
                b_key, b = ordered[1]
                edge = self.session.scalar(
                    select(ComparisonEdgeRecord).where(
                        ComparisonEdgeRecord.entity_a_key == a_key,
                        ComparisonEdgeRecord.entity_b_key == b_key,
                    )
                )
                if edge:
                    edge.count += 1
                    edge.last_asked = utc_now()
                else:
                    self.session.add(
                        ComparisonEdgeRecord(
                            id=new_id(),
                            entity_a=a,
                            entity_b=b,
                            entity_a_key=a_key,
                            entity_b_key=b_key,
                        )
                    )

    def query_detail(self, query_id: str) -> dict[str, Any] | None:
        query = self.session.get(QueryRecord, query_id)
        if query is None:
            return None
        sources = self.session.scalars(
            select(AnswerSourceRecord)
            .where(AnswerSourceRecord.query_id == query_id)
            .order_by(AnswerSourceRecord.citation_number)
        ).all()
        return {**_query_dict(query), "sources": [_model_dict(source) for source in sources]}

    def trace(self, query_id: str) -> dict[str, Any] | None:
        query = self.session.get(QueryRecord, query_id)
        if query is None:
            return None
        plan = self.session.scalar(
            select(QueryPlanRecord).where(QueryPlanRecord.query_id == query_id)
        )
        runs = self.session.scalars(
            select(RetrievalRunRecord)
            .where(RetrievalRunRecord.query_id == query_id)
            .order_by(RetrievalRunRecord.round_number)
        ).all()
        return {
            "query_id": query_id,
            "query_type": query.query_type,
            "standalone_query": query.standalone_query,
            "plan": json.loads(plan.plan_json) if plan else None,
            "retrieval_rounds": [_model_dict(run) for run in runs],
            "latency_ms": query.latency_ms,
        }

    def question_analytics(self, limit: int = 20) -> dict[str, Any]:
        common = self.session.execute(
            select(QueryRecord.normalized_query, func.count(QueryRecord.id).label("count"))
            .group_by(QueryRecord.normalized_query)
            .order_by(desc("count"))
            .limit(limit)
        ).all()
        by_type = self.session.execute(
            select(QueryRecord.query_type, func.count(QueryRecord.id)).group_by(
                QueryRecord.query_type
            )
        ).all()
        low_confidence = self.session.scalars(
            select(QueryRecord)
            .where(QueryRecord.answer_confidence.is_not(None))
            .order_by(QueryRecord.answer_confidence)
            .limit(limit)
        ).all()
        return {
            "most_common": [{"question": q, "count": count} for q, count in common],
            "by_type": {query_type: count for query_type, count in by_type},
            "low_confidence": [_query_dict(q) for q in low_confidence],
            "no_answer_count": self.session.scalar(
                select(func.count(QueryRecord.id)).where(QueryRecord.no_answer.is_(True))
            )
            or 0,
        }

    def comparison_analytics(self, limit: int = 20) -> list[dict[str, Any]]:
        edges = self.session.scalars(
            select(ComparisonEdgeRecord).order_by(desc(ComparisonEdgeRecord.count)).limit(limit)
        ).all()
        return [_model_dict(edge) for edge in edges]

    def list_queries(self, limit: int = 100) -> list[dict[str, Any]]:
        records = self.session.scalars(
            select(QueryRecord).order_by(desc(QueryRecord.created_at)).limit(limit)
        ).all()
        return [_query_dict(record) for record in records]

    def delete_document_record(self, document_id: str) -> None:
        self.session.execute(delete(DocumentRecord).where(DocumentRecord.id == document_id))


def _model_dict(record: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in record.__table__.columns:
        value = getattr(record, column.name)
        result[column.name] = value.isoformat() if isinstance(value, datetime) else value
    return result


def _query_dict(query: QueryRecord) -> dict[str, Any]:
    result = _model_dict(query)
    for key in (
        "entities_json",
        "comparison_targets_json",
        "comparison_dimensions_json",
        "subquestions_json",
    ):
        result[key.removesuffix("_json")] = json.loads(result.pop(key))
    return result
