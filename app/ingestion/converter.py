from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field


class ConvertedDocument(BaseModel):
    document_id: str
    filename: str
    source_path: str
    sha256: str
    markdown: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentConverter(Protocol):
    def convert(self, file_path: Path, document_id: str, sha256: str) -> ConvertedDocument: ...


class ConversionError(RuntimeError):
    pass
