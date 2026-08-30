from pathlib import Path
from typing import Any

import frontmatter
from pydantic import BaseModel, Field, field_validator


class OKFSource(BaseModel):
    resource: str
    id: str | None = None
    title: str | None = None
    author: str | None = None
    last_modified: str | None = None


class OKFGenerated(BaseModel):
    by: str
    at: str


class OKFConcept(BaseModel):
    concept_id: str
    path: Path
    type: str
    title: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: str | None = None
    generated: OKFGenerated | None = None
    sources: list[OKFSource] = Field(default_factory=list)
    body: str
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def nonempty_type(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("OKF type must be non-empty")
        return value.strip()

    def frontmatter(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": self.type,
            "title": self.title,
        }
        if self.description:
            data["description"] = self.description
        if self.tags:
            data["tags"] = self.tags
        if self.status:
            data["status"] = self.status
        if self.generated:
            data["generated"] = self.generated.model_dump(mode="json")
        if self.sources:
            data["sources"] = [
                source.model_dump(mode="json", exclude_none=True) for source in self.sources
            ]
        data.update(self.extra)
        return data

    @property
    def trust_tier(self) -> str:
        verified = self.extra.get("verified")
        if not verified:
            return "unverified"
        entries = verified if isinstance(verified, list) else [verified]
        if any(
            isinstance(item, dict) and str(item.get("by", "")).startswith("human:")
            for item in entries
        ):
            return "human-reviewed"
        return "machine-confirmed"


class OKFParseError(ValueError):
    pass


def parse_concept(path: Path, bundle_root: Path) -> OKFConcept:
    """Parse a v0.2 concept while preserving producer extension fields."""
    try:
        post = frontmatter.load(path)
    except Exception as exc:
        raise OKFParseError(f"Malformed YAML frontmatter in {path}: {exc}") from exc
    concept_type = post.metadata.get("type")
    if not isinstance(concept_type, str) or not concept_type.strip():
        raise OKFParseError(f"Missing non-empty OKF type in {path}")
    known = {"type", "title", "description", "tags", "status", "generated", "sources"}
    try:
        return OKFConcept(
            concept_id=path.relative_to(bundle_root).with_suffix("").as_posix(),
            path=path,
            type=concept_type,
            title=str(post.metadata.get("title") or path.stem.replace("-", " ").title()),
            description=post.metadata.get("description"),
            tags=list(post.metadata.get("tags") or []),
            status=post.metadata.get("status"),
            generated=post.metadata.get("generated"),
            sources=post.metadata.get("sources") or [],
            body=post.content.strip() + "\n",
            extra={key: value for key, value in post.metadata.items() if key not in known},
        )
    except Exception as exc:
        raise OKFParseError(f"Invalid OKF metadata in {path}: {exc}") from exc


def discover_concepts(bundle_root: Path) -> list[OKFConcept]:
    concepts = []
    for path in bundle_root.rglob("*.md"):
        if path.name in {"index.md", "log.md"}:
            continue
        concepts.append(parse_concept(path, bundle_root))
    return concepts
