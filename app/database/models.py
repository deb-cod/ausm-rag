from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.utils.time import utc_now


class Base(DeclarativeBase):
    pass


class SessionRecord(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MessageRecord(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DocumentRecord(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), index=True)
    safe_filename: Mapped[str] = mapped_column(String(255), unique=True)
    source_path: Mapped[str] = mapped_column(Text)
    markdown_path: Mapped[str] = mapped_column(Text)
    okf_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class QueryRecord(Base):
    __tablename__ = "queries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    original_query: Mapped[str] = mapped_column(Text)
    normalized_query: Mapped[str] = mapped_column(Text, index=True)
    standalone_query: Mapped[str] = mapped_column(Text)
    query_type: Mapped[str] = mapped_column(String(32), index=True)
    entities_json: Mapped[str] = mapped_column(Text, default="[]")
    comparison_targets_json: Mapped[str] = mapped_column(Text, default="[]")
    comparison_dimensions_json: Mapped[str] = mapped_column(Text, default="[]")
    subquestions_json: Mapped[str] = mapped_column(Text, default="[]")
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    no_answer: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class QueryPlanRecord(Base):
    __tablename__ = "query_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query_id: Mapped[str] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"), index=True)
    plan_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RetrievalRunRecord(Base):
    __tablename__ = "retrieval_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query_id: Mapped[str] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"), index=True)
    round_number: Mapped[int] = mapped_column(Integer)
    subquery: Mapped[str] = mapped_column(Text)
    strategy: Mapped[str] = mapped_column(String(32))
    dense_candidates: Mapped[int] = mapped_column(Integer, default=0)
    sparse_candidates: Mapped[int] = mapped_column(Integer, default=0)
    fused_candidates: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RetrievalResultRecord(Base):
    __tablename__ = "retrieval_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("retrieval_runs.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str] = mapped_column(String(36), index=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    channels_json: Mapped[str] = mapped_column(Text, default="[]")


class AnswerSourceRecord(Base):
    __tablename__ = "answer_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query_id: Mapped[str] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[str] = mapped_column(String(36), index=True)
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    citation_number: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)


class ComparisonEdgeRecord(Base):
    __tablename__ = "comparison_edges"
    __table_args__ = (UniqueConstraint("entity_a_key", "entity_b_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_a: Mapped[str] = mapped_column(String(255))
    entity_b: Mapped[str] = mapped_column(String(255))
    entity_a_key: Mapped[str] = mapped_column(String(255), index=True)
    entity_b_key: Mapped[str] = mapped_column(String(255), index=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    last_asked: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserFeedbackRecord(Base):
    __tablename__ = "user_feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query_id: Mapped[str] = mapped_column(ForeignKey("queries.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


Index("ix_queries_type_created", QueryRecord.query_type, QueryRecord.created_at)
