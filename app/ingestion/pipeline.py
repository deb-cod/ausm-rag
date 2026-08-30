import json
import shutil
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.database.models import DocumentRecord
from app.database.repository import Repository
from app.ingestion.chunker import StructureAwareChunker
from app.ingestion.converter import DocumentConverter
from app.ingestion.okf_builder import OKFBuilder
from app.ingestion.security import validate_upload
from app.knowledge.okf import discover_concepts
from app.retrieval.index import QdrantIndex
from app.utils.ids import new_id
from app.utils.time import utc_now


@dataclass
class IngestionResult:
    document: DocumentRecord
    duplicate: bool = False
    updated_document_id: str | None = None


class IngestionPipeline:
    def __init__(
        self,
        settings: Settings,
        session: Session,
        converter: DocumentConverter,
        okf_builder: OKFBuilder,
        chunker: StructureAwareChunker,
        index: QdrantIndex,
    ):
        self.settings = settings
        self.session = session
        self.repository = Repository(session)
        self.converter = converter
        self.okf_builder = okf_builder
        self.chunker = chunker
        self.index = index

    async def ingest(self, filename: str, content: bytes) -> IngestionResult:
        safe_name, sha256 = validate_upload(filename, content, self.settings)
        duplicate = self.repository.document_by_hash(sha256)
        if duplicate:
            return IngestionResult(document=duplicate, duplicate=True)

        existing = self.repository.document_by_filename(filename)
        updated_id = existing.id if existing else None

        document_id = new_id()
        source_dir = self.settings.source_dir / document_id
        source_dir.mkdir(parents=True, exist_ok=False)
        source_path = source_dir / safe_name
        source_path.write_bytes(content)
        concept = None
        try:
            converted = self.converter.convert(source_path, document_id, sha256)
            markdown_path = self.settings.markdown_dir / f"{document_id}.md"
            markdown_path.write_text(converted.markdown, encoding="utf-8")
            concept = self.okf_builder.build(converted, source_path)
            chunks = self.chunker.chunk(concept)
            await self.index.index_chunks(chunks)
            # Do not remove a working prior version until replacement conversion/indexing succeeds.
            if existing:
                await self.delete(existing.id)
            record = DocumentRecord(
                id=document_id,
                filename=filename,
                safe_filename=f"{document_id}/{safe_name}",
                source_path=str(source_path.resolve()),
                markdown_path=str(markdown_path.resolve()),
                okf_path=str(concept.path.resolve()),
                sha256=sha256,
                source_type=source_path.suffix.lower().lstrip("."),
                status="ready",
                chunk_count=len(chunks),
                metadata_json=json.dumps(converted.metadata),
            )
            self.session.add(record)
            self.session.commit()
            return IngestionResult(record, updated_document_id=updated_id)
        except Exception:
            self.session.rollback()
            with suppress(Exception):
                await self.index.delete_document(document_id)
            if concept is not None:
                self.okf_builder.remove_document(document_id, concept.path)
            shutil.rmtree(source_dir, ignore_errors=True)
            (self.settings.markdown_dir / f"{document_id}.md").unlink(missing_ok=True)
            raise

    async def delete(self, document_id: str) -> None:
        record = self.session.get(DocumentRecord, document_id)
        if record is None:
            raise LookupError(f"Document not found: {document_id}")
        await self.index.delete_document(document_id)
        self.okf_builder.remove_document(document_id, Path(record.okf_path))
        Path(record.markdown_path).unlink(missing_ok=True)
        source_dir = Path(record.source_path).parent
        if source_dir.parent.resolve() == self.settings.source_dir.resolve():
            shutil.rmtree(source_dir, ignore_errors=True)
        # Content-addressed embeddings may be shared, so they intentionally survive deletion.
        self.repository.delete_document_record(document_id)
        self.session.commit()

    async def rebuild_index(self) -> dict[str, int]:
        concepts = discover_concepts(self.settings.okf_dir)
        chunks = [chunk for concept in concepts for chunk in self.chunker.chunk(concept)]
        probe = await self.index.embeddings.embed("embedding dimension probe")
        await self.index.recreate_collection(len(probe))
        await self.index.index_chunks(chunks)
        counts: dict[str, int] = {}
        for chunk in chunks:
            counts[chunk.document_id] = counts.get(chunk.document_id, 0) + 1
        for record in self.repository.list_documents():
            record.chunk_count = counts.get(record.id, 0)
            record.updated_at = utc_now()
        self.session.commit()
        return {"concepts": len(concepts), "chunks": len(chunks)}
