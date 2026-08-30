from qdrant_client import models


def build_filter(
    *,
    document_ids: list[str] | None = None,
    concept_ids: list[str] | None = None,
    okf_types: list[str] | None = None,
    tags: list[str] | None = None,
    statuses: list[str] | None = None,
) -> models.Filter | None:
    must: list[models.FieldCondition] = []
    for key, values in (
        ("document_id", document_ids),
        ("concept_id", concept_ids),
        ("okf_type", okf_types),
        ("tags", tags),
        ("status", statuses),
    ):
        if values:
            must.append(models.FieldCondition(key=key, match=models.MatchAny(any=values)))
    return models.Filter(must=must) if must else None
