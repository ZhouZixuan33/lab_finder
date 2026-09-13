import pytest
from pydantic import ValidationError

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
        tags=[
            "Security & Privacy",
            "Computer Architecture & Systems",
            "Security & Privacy",
        ],
        homepage_source_id=page.source_id,
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
    assert validated.lab_url is None  # The independent homepage graph fills this later.
    assert validated.tags == ["Security & Privacy", "Computer Architecture & Systems"]
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
        tags=["Computer Architecture & Systems"],
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
        tags=["Computer Architecture & Systems"],
        evidence_source_ids=[page.source_id],
    )

    with pytest.raises(ResearchValidationError, match="identity"):
        validate_research_result(
            result,
            pages=[unverified_page],
            publications=[],
            registry=registry,
        )


@pytest.mark.parametrize(
    "tags",
    [
        ["Computer Architecture & Systems"],
        [
            "Computer Architecture & Systems",
            "Networking & Distributed Systems",
            "Security & Privacy",
        ],
    ],
)
def test_research_result_accepts_one_to_three_tags(tags: list[str]) -> None:
    result = ProfessorResearchResult(
        research_summary="A sufficiently detailed evidence-grounded research summary.",
        tags=tags,
        evidence_source_ids=["source_001"],
    )

    assert result.tags == tags


@pytest.mark.parametrize("count", [0, 4])
def test_research_result_requires_one_to_three_tags(count: int) -> None:
    tags = ["Computer Architecture & Systems"] * count

    with pytest.raises(ValidationError):
        ProfessorResearchResult(
            research_summary="A sufficiently detailed evidence-grounded research summary.",
            tags=tags,
            evidence_source_ids=["source_001"],
        )


@pytest.mark.parametrize(
    "invalid_tag",
    [
        "Congestion Control",
        "Systems for Everything",
        "computer architecture & systems",
    ],
)
def test_validation_rejects_tags_outside_the_controlled_taxonomy(
    invalid_tag: str,
) -> None:
    registry, page, _publication = evidence()
    result = ProfessorResearchResult(
        research_summary="A sufficiently detailed evidence-grounded research summary.",
        tags=[invalid_tag],
        evidence_source_ids=[page.source_id],
    )

    with pytest.raises(ResearchValidationError, match="controlled taxonomy"):
        validate_research_result(
            result,
            pages=[page],
            publications=[],
            registry=registry,
        )
