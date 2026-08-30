import asyncio
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_container, get_db
from app.api.schemas import QueryRequest
from app.container import AppContainer
from app.database.repository import Repository
from app.llm.ollama_client import OllamaError

router = APIRouter(prefix="/api", tags=["query"])


@router.post("/query")
async def query(
    request: QueryRequest,
    container: AppContainer = Depends(get_container),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        response = await container.orchestrator(db).run(request.session_id, request.query)
        return response.model_dump(mode="json")
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        if "qdrant" in type(exc).__module__.casefold() or "connection" in str(exc).casefold():
            raise HTTPException(
                status_code=503, detail=f"Retrieval service unavailable: {exc}"
            ) from exc
        raise


@router.post("/query/stream")
async def query_stream(
    request: QueryRequest, container: AppContainer = Depends(get_container)
) -> StreamingResponse:
    async def events():
        yield _event("query_analyzed", {"status": "started"})
        yield _event("retrieving", {"status": "started"})
        with container.session_factory() as session:
            try:
                response = await container.orchestrator(session).run(
                    request.session_id, request.query
                )
                yield _event("generating", {"status": "complete"})
                for token in response.answer.split(" "):
                    yield _event("token", {"text": token + " "})
                    await asyncio.sleep(0)
                yield _event(
                    "sources",
                    {"sources": [source.model_dump(mode="json") for source in response.sources]},
                )
                yield _event("done", response.model_dump(mode="json"))
            except Exception as exc:
                yield _event("error", {"detail": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/queries")
def queries(
    limit: Annotated[int, Query(ge=1, le=500)] = 100, db: Session = Depends(get_db)
) -> list[dict[str, Any]]:
    return Repository(db).list_queries(limit)


@router.get("/queries/{query_id}")
def query_detail(query_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = Repository(db).query_detail(query_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Query not found")
    return result


@router.get("/trace/{query_id}")
def trace(query_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = Repository(db).trace(query_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Query not found")
    return result


def _event(name: str, data: Any) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"
