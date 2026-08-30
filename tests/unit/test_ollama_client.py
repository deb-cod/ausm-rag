import json

import httpx
import pytest

from app.config import Settings
from app.llm.ollama_client import OllamaClient
from app.llm.schemas import QueryPlan


@pytest.mark.asyncio
async def test_structured_output_retries_malformed_json(tmp_path):
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            content = "not-json"
        else:
            content = QueryPlan(original_query="q", standalone_query="q").model_dump_json()
        return httpx.Response(200, json={"message": {"content": content}})

    settings = Settings(data_dir=tmp_path)
    client = OllamaClient(settings, transport=httpx.MockTransport(handler))
    try:
        result = await client.structured_chat([{"role": "user", "content": "q"}], QueryPlan)
        assert result.standalone_query == "q"
        assert calls == 2
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_embedding_batch_validation(tmp_path):
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[1.0, 2.0] for _ in payload["input"]]})

    client = OllamaClient(Settings(data_dir=tmp_path), transport=httpx.MockTransport(handler))
    try:
        assert await client.embed_batch(["a", "b"]) == [[1.0, 2.0], [1.0, 2.0]]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_chat_retries_an_empty_answer(tmp_path):
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = "" if calls == 1 else "Grounded answer [1]"
        return httpx.Response(200, json={"message": {"content": content}})

    client = OllamaClient(Settings(data_dir=tmp_path), transport=httpx.MockTransport(handler))
    try:
        answer = await client.chat([{"role": "user", "content": "Question"}])
        assert answer == "Grounded answer [1]"
        assert calls == 2
    finally:
        await client.close()
