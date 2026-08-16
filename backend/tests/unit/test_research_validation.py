import pytest

from lab_tracker.models.research import (
    ExtractedPage,
    IdentitySignals,
    OpenAlexPublication,
    ProfessorResearchResult,
    SearchHit,
)
from lab_tracker.services.research_sources import CandidateSourceRegistry
from lab_tracker.services.research_validation import (
    ResearchValidationError,
    validate_research_result,
)


def evidence() -> tuple[
    CandidateSourceRegistry,
    ExtractedPage,
    OpenAlexPublication,
]:
    registry = CandidateSourceRegistry()
    source = registry.register_hit(
        SearchHit(
            title="Alice Systems Lab",
            url="https://alice.example.edu/lab",
            snippet="Reliable systems research.",
        )
    )
    page = ExtractedPage(
        source_id=source.source_id,
        candidate_id=source.candidate_id,
        url=source.url,
        title=source.title,
        text="Alice Systems at UIUC researches reliable computing and secure accelerators.",
        identity_signals=IdentitySignals(name_match=True, affiliation_match=True),
    )
    publication = OpenAlexPublication(
        source_id="openalex:W1",
        openalex_id="W1",
        title="Reliable Accelerators",
        year=2026,
        publication_url="https://openalex.org/W1",
    )
    return registry, page, publication


def test_validation_resolves_only_verified_source_and_publication_ids() -> None:
    registry, page, publication = evidence()
    result = ProfessorResearchResult(
        research_summary=(
            "Alice Systems researches reliable computer architecture and secure accelerators."
        ),
        tags=["Reliable AI", "Computer Architecture", "Reliable AI"],
        homepage_source_id=page.source_id,
        lab_source_id=page.source_id,
        publication_source_ids=[publication.source_id],
        evidence_source_ids=[page.source_id],
        confidence=0.9,
    )

    validated = validate_research_result(
        result,
        pages=[page],
        publications=[publication],
        registry=registry,
    )

    assert validated.homepage_url == "https://alice.example.edu/lab"
    assert validated.lab_url == "https://alice.example.edu/lab"
    assert validated.tags == ["Reliable AI", "Computer Architecture"]
    assert [item.openalex_id for item in validated.publications] == ["W1"]
    assert validated.source_urls == ["https://alice.example.edu/lab"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_source_ids", ["source_999"]),
        ("homepage_source_id", "source_999"),
        ("publication_source_ids", ["openalex:W999"]),
    ],
)
def test_validation_rejects_unknown_model_generated_ids(field: str, value: object) -> None:
    registry, page, publication = evidence()
    result = ProfessorResearchResult(
        research_summary="A sufficiently detailed summary grounded in validated research evidence.",
        tags=["Systems"],
        evidence_source_ids=[page.source_id],
    ).model_copy(update={field: value})

    with pytest.raises(ResearchValidationError):
        validate_research_result(
            result,
            pages=[page],
            publications=[publication],
            registry=registry,
        )


def test_validation_rejects_summary_without_identity_matched_page_evidence() -> None:
    registry, page, _publication = evidence()
    unverified_page = page.model_copy(update={"identity_signals": IdentitySignals()})
    result = ProfessorResearchResult(
        research_summary="A sufficiently detailed summary that lacks verified identity evidence.",
        tags=["Systems"],
        evidence_source_ids=[page.source_id],
    )

    with pytest.raises(ResearchValidationError, match="identity"):
        validate_research_result(
            result,
            pages=[unverified_page],
            publications=[],
            registry=registry,
        )
