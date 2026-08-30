from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated configuration loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AUSM Smart RAG"
    app_env: str = "development"
    log_level: str = "INFO"
    data_dir: Path = Path("data")

    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "gemma4:e4b"
    ollama_embedding_model: str = "embeddinggemma"
    ollama_timeout_seconds: float = Field(default=180, gt=0)

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "smart_rag"
    sqlite_url: str = "sqlite:///data/database/smart_rag.db"

    chunk_target_tokens: int = Field(default=700, ge=100)
    chunk_overlap_tokens: int = Field(default=100, ge=0)
    dense_top_k: int = Field(default=20, ge=1)
    sparse_top_k: int = Field(default=20, ge=1)
    fused_top_k: int = Field(default=15, ge=1)
    rerank_top_k: int = Field(default=8, ge=1)
    max_retrieval_rounds: int = Field(default=2, ge=1, le=5)
    max_subqueries: int = Field(default=6, ge=1, le=12)
    max_graph_hops: int = Field(default=1, ge=0, le=3)
    enable_llm_rerank: bool = True
    min_evidence_score: float = Field(default=0.15, ge=0, le=1)

    max_upload_mb: int = Field(default=50, ge=1, le=1024)
    allowed_extensions: str = ".pdf,.docx,.pptx,.xlsx,.html,.htm,.txt,.md"

    @field_validator("ollama_base_url", "qdrant_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def source_dir(self) -> Path:
        return self.data_dir / "sources"

    @property
    def markdown_dir(self) -> Path:
        return self.data_dir / "markdown"

    @property
    def okf_dir(self) -> Path:
        return self.data_dir / "okf"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def allowed_extension_set(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_extensions.split(",") if item.strip()}

    def ensure_directories(self) -> None:
        for path in (
            self.source_dir,
            self.markdown_dir,
            self.okf_dir,
            self.okf_dir / "documents",
            self.okf_dir / "concepts",
            self.okf_dir / "references",
            self.cache_dir,
            self.data_dir / "database",
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
