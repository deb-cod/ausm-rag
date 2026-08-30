from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from qdrant_client import AsyncQdrantClient

from app.api import analytics, documents, health, ingest, query
from app.config import get_settings
from app.container import AppContainer
from app.database.session import create_database_engine, initialize_database, make_session_factory
from app.embeddings.ollama_embeddings import OllamaEmbeddings
from app.llm.ollama_client import OllamaClient
from app.logging import configure_logging
from app.retrieval.index import QdrantIndex


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_database_engine(settings)
    initialize_database(engine)
    factory = make_session_factory(engine)
    ollama = OllamaClient(settings)
    embeddings = OllamaEmbeddings(ollama)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url, timeout=30)
    index = QdrantIndex(settings, embeddings, qdrant)
    app.state.container = AppContainer(
        settings=settings,
        engine=engine,
        session_factory=factory,
        ollama=ollama,
        embeddings=embeddings,
        qdrant_client=qdrant,
        index=index,
    )
    yield
    await ollama.close()
    await qdrant.close()
    engine.dispose()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(analytics.router)


@app.exception_handler(Exception)
async def unhandled_exception(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
