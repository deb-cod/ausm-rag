import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_container, get_db
from app.api.ingest import make_pipeline
from app.container import AppContainer
from app.database.repository import Repository

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
def list_documents(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [
        {
            "document_id": item.id,
            "filename": item.filename,
            "sha256": item.sha256,
            "source_type": item.source_type,
            "status": item.status,
            "chunk_count": item.chunk_count,
            "metadata": json.loads(item.metadata_json),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
        for item in Repository(db).list_documents()
    ]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    container: AppContainer = Depends(get_container),
    db: Session = Depends(get_db),
) -> None:
    try:
        await make_pipeline(container, db).delete(document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
