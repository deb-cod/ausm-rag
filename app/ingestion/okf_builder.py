import shutil
from pathlib import Path

import frontmatter

from app.ingestion.converter import ConvertedDocument
from app.knowledge.okf import OKFConcept, OKFGenerated, OKFSource
from app.utils.ids import slugify
from app.utils.time import utc_iso


class OKFBuilder:
    """Persist converted knowledge as a conformant OKF v0.2 bundle."""

    def __init__(self, bundle_root: Path, model_name: str):
        self.bundle_root = bundle_root
        self.model_name = model_name

    def initialize_bundle(self) -> None:
        self.bundle_root.mkdir(parents=True, exist_ok=True)
        for child in ("documents", "concepts", "references"):
            (self.bundle_root / child).mkdir(parents=True, exist_ok=True)
        index = self.bundle_root / "index.md"
        if not index.exists():
            index.write_text(
                '---\nokf_version: "0.2"\n---\n\n# AUSM Smart RAG Knowledge Bundle\n\n'
                "Canonical local knowledge generated from explicitly ingested documents.\n",
                encoding="utf-8",
            )

    def build(self, document: ConvertedDocument, original_source: Path) -> OKFConcept:
        self.initialize_bundle()
        slug = slugify(Path(document.filename).stem)
        doc_dir = self.bundle_root / "documents" / f"{slug}-{document.document_id[:8]}"
        ref_dir = self.bundle_root / "references" / document.document_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        ref_dir.mkdir(parents=True, exist_ok=True)
        # In OKF every non-reserved `.md` file is a concept. Preserve raw Markdown sources under a
        # neutral suffix so they remain reference artifacts rather than invalid concept documents.
        reference_name = (
            f"{original_source.name}.source"
            if original_source.suffix.casefold() == ".md"
            else original_source.name
        )
        reference_path = ref_dir / reference_name
        shutil.copy2(original_source, reference_path)

        title = str(document.metadata.get("title") or Path(document.filename).stem)
        concept_path = doc_dir / f"{slug}.md"
        concept = OKFConcept(
            concept_id=concept_path.relative_to(self.bundle_root).with_suffix("").as_posix(),
            path=concept_path,
            type="Reference",
            title=title,
            description=f"Converted content of {document.filename}.",
            tags=[document.metadata.get("source_type", "document"), "ingested"],
            status="draft",
            generated=OKFGenerated(by="process:smart-rag-ingestion", at=utc_iso()),
            sources=[
                OKFSource(
                    id=document.document_id,
                    resource="/" + reference_path.relative_to(self.bundle_root).as_posix(),
                    title=document.filename,
                )
            ],
            body=document.markdown,
            extra={
                "document_id": document.document_id,
                "source_sha256": document.sha256,
            },
        )
        post = frontmatter.Post(concept.body, **concept.frontmatter())
        concept_path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
        (doc_dir / "index.md").write_text(
            f"# {title}\n\n- [{title}]({concept_path.name}) — converted source document.\n",
            encoding="utf-8",
        )
        self._refresh_root_index()
        return concept

    def remove_document(self, document_id: str, okf_path: Path) -> None:
        if okf_path.parent.exists():
            shutil.rmtree(okf_path.parent)
        reference_dir = self.bundle_root / "references" / document_id
        if reference_dir.exists():
            shutil.rmtree(reference_dir)
        self._refresh_root_index()

    def _refresh_root_index(self) -> None:
        entries = []
        documents_dir = self.bundle_root / "documents"
        for path in sorted(documents_dir.glob("*/index.md")):
            relative = path.relative_to(self.bundle_root).as_posix()
            entries.append(f"- [{path.parent.name}]({relative})")
        content = (
            '---\nokf_version: "0.2"\n---\n\n# AUSM Smart RAG Knowledge Bundle\n\n'
            "Canonical local knowledge generated from explicitly ingested documents.\n\n"
            "## Documents\n\n"
            + ("\n".join(entries) if entries else "No documents have been ingested.")
            + "\n"
        )
        (self.bundle_root / "index.md").write_text(content, encoding="utf-8")
