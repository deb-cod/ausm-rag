from pathlib import Path

from markitdown import MarkItDown

from app.ingestion.converter import ConversionError, ConvertedDocument


class MarkItDownConverter:
    """Convert explicitly validated local files to normalized Markdown."""

    def __init__(self) -> None:
        self._converter = MarkItDown(enable_plugins=False)

    def convert(self, file_path: Path, document_id: str, sha256: str) -> ConvertedDocument:
        try:
            result = self._converter.convert_local(file_path)
            markdown = result.text_content.strip()
        except Exception as exc:
            raise ConversionError(f"MarkItDown could not convert {file_path.name}: {exc}") from exc
        if not markdown:
            raise ConversionError(f"Document conversion produced no text: {file_path.name}")
        return ConvertedDocument(
            document_id=document_id,
            filename=file_path.name,
            source_path=str(file_path.resolve()),
            sha256=sha256,
            markdown=markdown + "\n",
            metadata={
                "title": getattr(result, "title", None),
                "source_type": file_path.suffix.lower().lstrip("."),
            },
        )
