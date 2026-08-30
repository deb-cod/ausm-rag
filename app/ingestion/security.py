import hashlib
from pathlib import Path

from app.config import Settings
from app.utils.ids import slugify


class InvalidUpload(ValueError):
    pass


def validate_upload(filename: str, content: bytes, settings: Settings) -> tuple[str, str]:
    basename = Path(filename).name
    if basename != filename or filename in {"", ".", ".."}:
        raise InvalidUpload("Filename must not contain a path")
    suffix = Path(basename).suffix.lower()
    if suffix not in settings.allowed_extension_set:
        raise InvalidUpload(f"Unsupported extension: {suffix or '(none)'}")
    if not content:
        raise InvalidUpload("The uploaded file is empty")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise InvalidUpload(f"Upload exceeds the {settings.max_upload_mb} MB limit")
    if suffix == ".pdf" and not content.startswith(b"%PDF-"):
        raise InvalidUpload("File extension and PDF content do not match")
    if suffix in {".docx", ".pptx", ".xlsx"} and not content.startswith(b"PK"):
        raise InvalidUpload("Office Open XML uploads must be valid ZIP-based files")
    if suffix in {".txt", ".md", ".html", ".htm"} and b"\x00" in content[:8192]:
        raise InvalidUpload("Text-like upload appears to contain binary data")
    safe = f"{slugify(Path(basename).stem)}{suffix}"
    return safe, hashlib.sha256(content).hexdigest()
