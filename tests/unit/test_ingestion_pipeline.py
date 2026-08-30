from pathlib import Path

import pytest

from app.config import Settings
from app.database.models import Base
from app.database.session import create_database_engine, make_session_factory
from app.ingestion.chunker import StructureAwareChunker
from app.ingestion.markitdown_converter import MarkItDownConverter
from app.ingestion.okf_builder import OKFBuilder
from app.ingestion.pipeline import IngestionPipeline
from app.knowledge.okf import discover_concepts


class FakeIndex:
    def __init__(self):
        self.by_document: dict[str, list] = {}

    async def index_chunks(self, chunks):
        for chunk in chunks:
            self.by_document.setdefault(chunk.document_id, []).append(chunk)

    async def delete_document(self, document_id):
        self.by_document.pop(document_id, None)


def make_pipeline(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "data",
        sqlite_url=f"sqlite:///{(tmp_path / 'rag.db').as_posix()}",
        chunk_target_tokens=100,
        chunk_overlap_tokens=10,
    )
    settings.ensure_directories()
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    index = FakeIndex()
    pipeline = IngestionPipeline(
        settings,
        session,
        MarkItDownConverter(),
        OKFBuilder(settings.okf_dir, settings.ollama_llm_model),
        StructureAwareChunker(100, 10),
        index,  # type: ignore[arg-type]
    )
    return pipeline, session, index, settings, engine


@pytest.mark.asyncio
async def test_convert_duplicate_update_and_delete(tmp_path: Path):
    pipeline, session, index, settings, engine = make_pipeline(tmp_path)
    try:
        first = await pipeline.ingest("policy.md", b"# Leave\n\nEmployees receive 20 days.")
        assert not first.duplicate
        assert first.document.id in index.by_document
        assert Path(first.document.markdown_path).exists()
        assert Path(first.document.okf_path).exists()
        assert len(discover_concepts(settings.okf_dir)) == 1

        duplicate = await pipeline.ingest("copy.md", b"# Leave\n\nEmployees receive 20 days.")
        assert duplicate.duplicate
        assert duplicate.document.id == first.document.id

        updated = await pipeline.ingest("policy.md", b"# Leave\n\nEmployees receive 25 days.")
        assert updated.updated_document_id == first.document.id
        assert updated.document.id != first.document.id
        assert first.document.id not in index.by_document

        document_id = updated.document.id
        source_path = Path(updated.document.source_path)
        await pipeline.delete(document_id)
        assert session.get(type(updated.document), document_id) is None
        assert not source_path.exists()
        assert document_id not in index.by_document
        assert (settings.okf_dir / "index.md").exists()
    finally:
        session.close()
        engine.dispose()
