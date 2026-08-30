from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.database.models import Base
from app.database.repository import Repository
from app.database.session import create_database_engine
from app.llm.schemas import QueryPlan, QueryType


def test_comparison_edges_are_order_independent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = Repository(session)
        repository.record_comparisons(["Qdrant", "Chroma"])
        repository.record_comparisons(["chroma", "qdrant"])
        session.commit()
        edges = repository.comparison_analytics()
        assert len(edges) == 1
        assert edges[0]["count"] == 2


def test_query_analytics_stores_structured_plan():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = Repository(session)
        plan = QueryPlan(
            original_query="A vs B",
            standalone_query="A vs B",
            query_type=QueryType.COMPARISON,
            comparison_targets=["A", "B"],
            retrieval_strategy="comparison",
        )
        query = repository.create_query("session", plan)
        repository.add_query_plan(query.id, plan)
        session.commit()
        detail = repository.query_detail(query.id)
        assert detail is not None
        assert detail["comparison_targets"] == ["A", "B"]


def test_retrieval_run_respects_sqlite_foreign_keys(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        sqlite_url=f"sqlite:///{(tmp_path / 'foreign-keys.db').as_posix()}",
    )
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = Repository(session)
        query = repository.create_query(
            "session",
            QueryPlan(original_query="Question", standalone_query="Question"),
        )
        session.commit()
        result = SimpleNamespace(
            chunk_id="chunk", document_id="document", score=0.8, channels=["dense"]
        )
        repository.add_retrieval_run(query.id, 1, "Question", "standard", 1, 0, [result], 10.0)
        session.commit()
        trace = repository.trace(query.id)
        assert trace is not None
        assert len(trace["retrieval_rounds"]) == 1
    engine.dispose()
