"""Deterministic validation and resolution of model-selected evidence IDs."""

from lab_tracker.models.research import (
    ExtractedPage,
    ProfessorResearchResult,
    ValidatedProfessorResearch,
)
from lab_tracker.services.research_sources import CandidateSourceRegistry, UnknownSourceError
from lab_tracker.services.tag_taxonomy import ALLOWED_PROFESSOR_TAG_SET


class ResearchValidationError(ValueError):
    pass


def _identity_matched(page: ExtractedPage) -> bool:
    signals = page.identity_signals
    return signals.name_match or signals.email_match or signals.affiliation_match


def validate_research_result(
    result: ProfessorResearchResult,
    *,
    pages: list[ExtractedPage],
    registry: CandidateSourceRegistry,
) -> ValidatedProfessorResearch:
    page_by_id = {page.source_id: page for page in pages}

    evidence_ids = list(dict.fromkeys(result.evidence_source_ids))
    evidence_pages: list[ExtractedPage] = []
    for source_id in evidence_ids:
        page = page_by_id.get(source_id)
        if page is None:
            raise ResearchValidationError(f"evidence source ID was not extracted: {source_id}")
        try:
            registered = registry.get(source_id)
        except UnknownSourceError as error:
            raise ResearchValidationError(f"evidence source ID is unknown: {source_id}") from error
        if registered.url != page.url:
            raise ResearchValidationError(f"evidence source URL mismatch: {source_id}")
        evidence_pages.append(page)

    if not evidence_pages:
        raise ResearchValidationError("reliable research evidence is required")
    if not any(_identity_matched(page) and len(page.text) >= 30 for page in evidence_pages):
        raise ResearchValidationError("identity-matched page evidence is required")

    def resolve_link(source_id: str | None, label: str) -> str | None:
        if source_id is None:
            return None
        if source_id not in evidence_ids:
            raise ResearchValidationError(f"{label} source must also be cited as evidence")
        page = page_by_id.get(source_id)
        if page is None or not _identity_matched(page):
            raise ResearchValidationError(f"{label} source lacks identity evidence")
        try:
            return registry.get(source_id).url
        except UnknownSourceError as error:
            raise ResearchValidationError(f"{label} source ID is unknown: {source_id}") from error

    tags: list[str] = []
    seen_tags: set[str] = set()
    for tag in result.tags:
        normalized = " ".join(tag.split())
        key = normalized.casefold()
        if normalized and key not in seen_tags:
            tags.append(normalized)
            seen_tags.add(key)
    if not tags:
        raise ResearchValidationError("at least one non-empty research tag is required")
    invalid_tags = [tag for tag in tags if tag not in ALLOWED_PROFESSOR_TAG_SET]
    if invalid_tags:
        invalid_text = ", ".join(repr(tag[:100]) for tag in invalid_tags)
        raise ResearchValidationError(
            "tags must use exact values from the controlled taxonomy; "
            f"invalid tags: {invalid_text}"
        )

    prospective_quote = None
    prospective_url = None
    if (
        result.prospective_students_quote is not None
        or result.prospective_students_source_id is not None
    ):
        if not result.prospective_students_quote or not result.prospective_students_source_id:
            raise ResearchValidationError("prospective students requires both quote and source ID")
        prospective_url = resolve_link(
            result.prospective_students_source_id, "prospective students"
        )
        prospective_quote = " ".join(result.prospective_students_quote.split())
        page_text = " ".join(page_by_id[result.prospective_students_source_id].text.split())
        if not prospective_quote or prospective_quote not in page_text:
            raise ResearchValidationError("prospective students quote must occur in the cited page")

    return ValidatedProfessorResearch(
        prospective_students_quote=prospective_quote,
        prospective_students_source_url=prospective_url,
        research_summary=" ".join(result.research_summary.split()),
        tags=tags,
        homepage_url=resolve_link(result.homepage_source_id, "homepage"),
        source_urls=[registry.get(source_id).url for source_id in evidence_ids],
        confidence=result.confidence,
    )
