import re
from collections import defaultdict, deque
from pathlib import Path

from app.knowledge.okf import OKFConcept

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md)(?:#[^)]+)?\)")


class KnowledgeGraph:
    """Best-effort OKF hierarchy and Markdown-link relationship graph."""

    def __init__(self, concepts: list[OKFConcept], bundle_root: Path):
        self.concepts = {concept.concept_id: concept for concept in concepts}
        self.edges: dict[str, set[str]] = defaultdict(set)
        for concept in concepts:
            parts = concept.concept_id.split("/")
            if len(parts) > 1:
                siblings = [
                    other.concept_id
                    for other in concepts
                    if other.concept_id != concept.concept_id
                    and other.concept_id.rsplit("/", 1)[0] == concept.concept_id.rsplit("/", 1)[0]
                ]
                self.edges[concept.concept_id].update(siblings)
            for target in LINK_RE.findall(concept.body):
                candidate = (concept.path.parent / target).resolve()
                try:
                    target_id = (
                        candidate.relative_to(bundle_root.resolve()).with_suffix("").as_posix()
                    )
                except ValueError:
                    continue
                if target_id in self.concepts:
                    self.edges[concept.concept_id].add(target_id)
                    self.edges[target_id].add(concept.concept_id)

    def expand(self, concept_ids: list[str], max_hops: int = 1) -> list[str]:
        seen = set(concept_ids)
        queue = deque((concept_id, 0) for concept_id in concept_ids)
        while queue:
            current, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for neighbor in self.edges.get(current, set()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, depth + 1))
        return list(seen)
