import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.llm.schemas import OllamaTags

T = TypeVar("T", bound=BaseModel)


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    """Single retrying async client for chat, structured output, and embeddings."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=httpx.Timeout(settings.ollama_timeout_seconds),
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = await self._client.post(path, json=payload)
                response.raise_for_status()
                return response
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(0.25)
        raise OllamaError(f"Ollama request failed: {last_error}") from last_error

    async def tags(self) -> OllamaTags:
        try:
            response = await self._client.get("/api/tags", timeout=10)
            response.raise_for_status()
            return OllamaTags.model_validate(response.json())
        except (httpx.HTTPError, ValidationError) as exc:
            raise OllamaError(f"Unable to list Ollama models: {exc}") from exc

    async def chat(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.1,
        model: str | None = None,
    ) -> str:
        payload_messages = list(messages)
        for attempt in range(2):
            response = await self._post(
                "/api/chat",
                {
                    "model": model or self.settings.ollama_llm_model,
                    "messages": payload_messages,
                    "think": False,
                    "stream": False,
                    "options": {"temperature": temperature},
                },
            )
            try:
                content = str(response.json()["message"]["content"]).strip()
            except (KeyError, TypeError, ValueError) as exc:
                raise OllamaError("Ollama returned an invalid chat response") from exc
            if content:
                return content
            if attempt == 0:
                payload_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your response was empty. Return a concise answer grounded in the "
                            "provided evidence, with citation markers."
                        ),
                    }
                )
        raise OllamaError("Ollama returned an empty answer after one retry")

    async def structured_chat(
        self,
        messages: Sequence[dict[str, str]],
        schema: type[T],
        *,
        temperature: float = 0.0,
    ) -> T:
        payload_messages = list(messages)
        for attempt in range(2):
            response = await self._post(
                "/api/chat",
                {
                    "model": self.settings.ollama_llm_model,
                    "messages": payload_messages,
                    "think": False,
                    "format": schema.model_json_schema(),
                    "stream": False,
                    "options": {"temperature": temperature},
                },
            )
            try:
                content = response.json()["message"]["content"]
                return schema.model_validate_json(content)
            except (KeyError, TypeError, json.JSONDecodeError, ValidationError) as exc:
                if attempt == 0:
                    payload_messages.append(
                        {
                            "role": "user",
                            "content": " ".join(
                                (
                                    "Your previous output was invalid. Return only JSON",
                                    "conforming exactly to this schema:",
                                    json.dumps(schema.model_json_schema()),
                                    f"Error: {exc}",
                                )
                            ),
                        }
                    )
                    continue
                raise OllamaError(f"Invalid structured output after correction: {exc}") from exc
        raise OllamaError("Structured output failed")

    async def embed(self, text: str) -> list[float]:
        vectors = await self.embed_batch([text])
        return vectors[0]

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._post(
            "/api/embed",
            {"model": self.settings.ollama_embedding_model, "input": list(texts)},
        )
        try:
            vectors = response.json()["embeddings"]
            if len(vectors) != len(texts) or any(not vector for vector in vectors):
                raise ValueError("embedding count or dimension mismatch")
            return [[float(value) for value in vector] for vector in vectors]
        except (KeyError, TypeError, ValueError) as exc:
            raise OllamaError(f"Ollama returned invalid embeddings: {exc}") from exc

    async def stream_chat(
        self, messages: Sequence[dict[str, str]], *, temperature: float = 0.1
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.settings.ollama_llm_model,
            "messages": list(messages),
            "think": False,
            "stream": True,
            "options": {"temperature": temperature},
        }
        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise OllamaError(f"Ollama streaming request failed: {exc}") from exc
