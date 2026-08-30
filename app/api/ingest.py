from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_container, get_db
from app.container import AppContainer
from app.ingestion.chunker import StructureAwareChunker
from app.ingestion.converter import ConversionError
from app.ingestion.markitdown_converter import MarkItDownConverter
from app.ingestion.okf_builder import OKFBuilder
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.security import InvalidUpload

router = APIRouter(prefix="/api", tags=["ingestion"])


def make_pipeline(container: AppContainer, db: Session) -> IngestionPipeline:
    return IngestionPipeline(
        settings=container.settings,
        session=db,
        converter=MarkItDownConverter(),
        okf_builder=OKFBuilder(container.settings.okf_dir, container.settings.ollama_llm_model),
        chunker=StructureAwareChunker(
            container.settings.chunk_target_tokens, container.settings.chunk_overlap_tokens
        ),
        index=container.index,
    )


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest(
    file: Annotated[UploadFile, File()],
    container: AppContainer = Depends(get_container),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    max_bytes = container.settings.max_upload_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    try:
        result = await make_pipeline(container, db).ingest(file.filename or "", content)
    except (InvalidUpload, ConversionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    record = result.document
    return {
        "document_id": record.id,
        "filename": record.filename,
        "sha256": record.sha256,
        "chunks": record.chunk_count,
        "duplicate": result.duplicate,
        "updated_document_id": result.updated_document_id,
        "status": record.status,
    }


@router.post("/reindex")
async def reindex(
    container: AppContainer = Depends(get_container), db: Session = Depends(get_db)
) -> dict[str, Any]:
    return await make_pipeline(container, db).rebuild_index()
