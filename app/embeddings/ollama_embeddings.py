from collections.abc import Sequence

from app.llm.ollama_client import OllamaClient


class OllamaEmbeddings:
    def __init__(self, client: OllamaClient):
        self.client = client

    async def embed(self, text: str) -> list[float]:
        return await self.client.embed(text)

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return await self.client.embed_batch(texts)
