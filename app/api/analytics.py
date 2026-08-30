from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.database.models import DocumentRecord, QueryRecord, RetrievalRunRecord
from app.database.repository import Repository

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics/questions")
def question_analytics(
    limit: Annotated[int, Query(ge=1, le=100)] = 20, db: Session = Depends(get_db)
) -> dict[str, Any]:
    return Repository(db).question_analytics(limit)


@router.get("/analytics/comparisons")
def comparison_analytics(
    limit: Annotated[int, Query(ge=1, le=100)] = 20, db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    return Repository(db).comparison_analytics(limit)


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {
        "documents_indexed": db.scalar(select(func.count(DocumentRecord.id))) or 0,
        "chunks_indexed": db.scalar(select(func.sum(DocumentRecord.chunk_count))) or 0,
        "total_questions": db.scalar(select(func.count(QueryRecord.id))) or 0,
        "comparison_queries": db.scalar(
            select(func.count(QueryRecord.id)).where(QueryRecord.query_type == "comparison")
        )
        or 0,
        "no_answer_count": db.scalar(
            select(func.count(QueryRecord.id)).where(QueryRecord.no_answer.is_(True))
        )
        or 0,
        "average_query_latency_ms": db.scalar(select(func.avg(QueryRecord.latency_ms))) or 0,
        "average_retrieval_latency_ms": db.scalar(select(func.avg(RetrievalRunRecord.duration_ms)))
        or 0,
        "queries_by_type": dict(
            db.execute(
                select(QueryRecord.query_type, func.count(QueryRecord.id)).group_by(
                    QueryRecord.query_type
                )
            ).all()
        ),
    }
