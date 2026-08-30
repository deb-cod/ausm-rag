import re
import unicodedata
from uuid import UUID, uuid4, uuid5

NAMESPACE = UUID("d2754bda-c39f-4b98-bdb7-ec5212eab6af")


def new_id() -> str:
    return str(uuid4())


def stable_uuid(value: str) -> str:
    return str(uuid5(NAMESPACE, value))


def slugify(value: str, fallback: str = "document") -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug[:100] or fallback
