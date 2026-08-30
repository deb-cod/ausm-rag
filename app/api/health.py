from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.api.dependencies import get_container
from app.container import AppContainer
from app.llm.ollama_client import OllamaError

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(container: AppContainer = Depends(get_container)) -> dict[str, Any]:
    components: dict[str, dict[str, Any]] = {"api": {"status": "ok"}}
    try:
        with container.session_factory() as session:
            session.execute(text("SELECT 1"))
        components["sqlite"] = {"status": "ok"}
    except Exception as exc:
        components["sqlite"] = {"status": "error", "detail": str(exc)}
    components["qdrant"] = {
        "status": "ok" if await container.index.healthy() else "error",
        "url": container.settings.qdrant_url,
    }
    try:
        tags = await container.ollama.tags()
        names = {model.name for model in tags.models} | {
            model.model for model in tags.models if model.model
        }
        normalized_names = {name.removesuffix(":latest") for name in names}
        components["ollama"] = {"status": "ok", "url": container.settings.ollama_base_url}
        components["llm_model"] = {
            "status": "ok"
            if container.settings.ollama_llm_model in normalized_names
            or container.settings.ollama_llm_model in names
            else "missing",
            "model": container.settings.ollama_llm_model,
        }
        components["embedding_model"] = {
            "status": "ok"
            if container.settings.ollama_embedding_model in normalized_names
            or container.settings.ollama_embedding_model in names
            else "missing",
            "model": container.settings.ollama_embedding_model,
        }
    except OllamaError as exc:
        components["ollama"] = {"status": "error", "detail": str(exc)}
        components["llm_model"] = {"status": "unknown"}
        components["embedding_model"] = {"status": "unknown"}
    overall = "ok" if all(item["status"] == "ok" for item in components.values()) else "degraded"
    return {"status": overall, "components": components}
