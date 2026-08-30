import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app.knowledge.okf import OKFConcept
from app.utils.ids import stable_uuid
from app.utils.text import estimate_tokens

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LIST_RE = re.compile(r"^\s*(?:[-*+] |\d+[.)] )")


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    concept_id: str
    parent_id: str | None = None
    heading: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    content: str
    chunk_index: int
    source_file: str
    source_type: str
    tags: list[str] = Field(default_factory=list)
    okf_type: str
    status: str | None = None
    generated_at: str | None = None
    trust_tier: str = "unverified"
    stale_after: str | None = None
    is_stale: bool = False
    source_sha256: str
    page: int | None = None
    slide: int | None = None
    sheet: str | None = None


@dataclass
class Block:
    text: str
    heading_path: list[str] = field(default_factory=list)
    atomic: bool = False


class StructureAwareChunker:
    """Chunk Markdown by semantic blocks while keeping tables and code fences intact."""

    def __init__(self, target_tokens: int = 700, overlap_tokens: int = 100):
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, concept: OKFConcept) -> list[Chunk]:
        blocks = self._blocks(concept.body)
        groups: list[tuple[list[str], str]] = []
        current: list[Block] = []
        current_tokens = 0
        for block in blocks:
            block_tokens = estimate_tokens(block.text)
            if current and current_tokens + block_tokens > self.target_tokens:
                groups.append((current[0].heading_path, "\n\n".join(item.text for item in current)))
                current = self._overlap(current)
                current_tokens = sum(estimate_tokens(item.text) for item in current)
            if block_tokens > self.target_tokens and not block.atomic:
                for piece in self._split_large_prose(block):
                    piece_tokens = estimate_tokens(piece.text)
                    if current and current_tokens + piece_tokens > self.target_tokens:
                        groups.append(
                            (current[0].heading_path, "\n\n".join(item.text for item in current))
                        )
                        current = self._overlap(current)
                        current_tokens = sum(estimate_tokens(item.text) for item in current)
                    current.append(piece)
                    current_tokens += piece_tokens
            else:
                current.append(block)
                current_tokens += block_tokens
        if current:
            groups.append((current[0].heading_path, "\n\n".join(item.text for item in current)))

        document_id = str(concept.extra.get("document_id", concept.concept_id))
        sha = str(concept.extra.get("source_sha256", ""))
        generated_at = concept.generated.at if concept.generated else None
        stale_after = concept.extra.get("stale_after")
        stale_after_text = str(stale_after) if stale_after else None
        is_stale = _is_stale(stale_after_text)
        source_file = concept.sources[0].title if concept.sources else concept.path.name
        source_type = Path(source_file or "").suffix.lstrip(".") or "markdown"
        chunks = []
        for index, (heading_path, content) in enumerate(groups):
            clean = content.strip()
            if not clean:
                continue
            chunks.append(
                Chunk(
                    chunk_id=stable_uuid(f"{concept.concept_id}:{index}:{sha}"),
                    document_id=document_id,
                    concept_id=concept.concept_id,
                    parent_id=stable_uuid(f"parent:{concept.concept_id}"),
                    heading=heading_path[-1] if heading_path else concept.title,
                    heading_path=heading_path,
                    content=clean,
                    chunk_index=index,
                    source_file=source_file or concept.path.name,
                    source_type=source_type,
                    tags=concept.tags,
                    okf_type=concept.type,
                    status=concept.status,
                    generated_at=generated_at,
                    trust_tier=concept.trust_tier,
                    stale_after=stale_after_text,
                    is_stale=is_stale,
                    source_sha256=sha,
                )
            )
        return chunks

    def _blocks(self, markdown: str) -> list[Block]:
        lines = markdown.splitlines()
        blocks: list[Block] = []
        headings: list[str] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if not line.strip():
                index += 1
                continue
            heading = HEADING_RE.match(line)
            if heading:
                level = len(heading.group(1))
                headings = headings[: level - 1] + [heading.group(2).strip()]
                blocks.append(Block(line, headings.copy(), atomic=True))
                index += 1
                continue
            if line.lstrip().startswith("```") or line.lstrip().startswith("~~~"):
                marker = line.lstrip()[:3]
                gathered = [line]
                index += 1
                while index < len(lines):
                    gathered.append(lines[index])
                    if lines[index].lstrip().startswith(marker):
                        index += 1
                        break
                    index += 1
                blocks.append(Block("\n".join(gathered), headings.copy(), atomic=True))
                continue
            if (
                "|" in line
                and index + 1 < len(lines)
                and re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1])
            ):
                gathered = [line, lines[index + 1]]
                index += 2
                while index < len(lines) and "|" in lines[index] and lines[index].strip():
                    gathered.append(lines[index])
                    index += 1
                blocks.append(Block("\n".join(gathered), headings.copy(), atomic=True))
                continue
            if LIST_RE.match(line):
                gathered = [line]
                index += 1
                while index < len(lines) and (
                    LIST_RE.match(lines[index]) or lines[index].startswith("  ")
                ):
                    gathered.append(lines[index])
                    index += 1
                blocks.append(Block("\n".join(gathered), headings.copy(), atomic=True))
                continue
            gathered = [line]
            index += 1
            while (
                index < len(lines) and lines[index].strip() and not HEADING_RE.match(lines[index])
            ):
                if lines[index].lstrip().startswith(("```", "~~~")) or LIST_RE.match(lines[index]):
                    break
                gathered.append(lines[index])
                index += 1
            blocks.append(Block("\n".join(gathered), headings.copy()))
        return blocks

    def _split_large_prose(self, block: Block) -> list[Block]:
        sentences = re.split(r"(?<=[.!?])\s+", block.text)
        result: list[Block] = []
        current: list[str] = []
        count = 0
        for sentence in sentences:
            tokens = estimate_tokens(sentence)
            if current and count + tokens > self.target_tokens:
                result.append(Block(" ".join(current), block.heading_path))
                current, count = [], 0
            current.append(sentence)
            count += tokens
        if current:
            result.append(Block(" ".join(current), block.heading_path))
        return result

    def _overlap(self, blocks: list[Block]) -> list[Block]:
        if not self.overlap_tokens:
            return []
        selected: list[Block] = []
        total = 0
        for block in reversed(blocks):
            tokens = estimate_tokens(block.text)
            if selected and total + tokens > self.overlap_tokens:
                break
            selected.append(block)
            total += tokens
        return list(reversed(selected))


def _is_stale(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return datetime.now(UTC) >= parsed
    except ValueError:
        return False
