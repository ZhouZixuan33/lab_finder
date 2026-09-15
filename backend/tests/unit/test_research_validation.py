import pytest
from pydantic import ValidationError

from lab_tracker.models.research import (
    ExtractedPage,
    IdentitySignals,
    ProfessorResearchResult,
    SearchHit,
)
from lab_tracker.services.research_sources import CandidateSourceRegistry
from lab_tracker.services.research_validation import (
    ResearchValidationError,
    validate_research_result,
)
from lab_tracker.services.tag_taxonomy import ALLOWED_PROFESSOR_TAGS


def evidence() -> tuple[
    CandidateSourceRegistry,
    ExtractedPage,
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
    return registry, page


@pytest.mark.parametrize("tag", ALLOWED_PROFESSOR_TAGS)
def test_validation_accepts_each_current_category(tag: str) -> None:
    registry, page = evidence()
    result = ProfessorResearchResult(
        research_summary="A sufficiently detailed evidence-grounded research summary.",
        tags=[tag],
        evidence_source_ids=[page.source_id],
    )

    validated = validate_research_result(result, pages=[page], registry=registry)

    assert validated.tags == [tag]


def test_validation_resolves_only_verified_webpage_ids() -> None:
    registry, page = evidence()
    result = ProfessorResearchResult(
        research_summary=(
            "Alice Systems researches reliable computer architecture and secure accelerators."
        ),
        tags=[
            "Security & Privacy",
            "Computer Architecture & Hardware",
            "Security & Privacy",
        ],
        homepage_source_id=page.source_id,
        evidence_source_ids=[page.source_id],
        confidence=0.9,
    )

    validated = validate_research_result(
        result,
        pages=[page],
        registry=registry,
    )

    assert validated.homepage_url == "https://alice.example.edu/lab"
    assert validated.lab_url is None  # The orchestrator attaches the discovered homepage.
    assert validated.tags == ["Security & Privacy", "Computer Architecture & Hardware"]
    assert validated.publications == []
    assert validated.source_urls == ["https://alice.example.edu/lab"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_source_ids", ["source_999"]),
        ("homepage_source_id", "source_999"),
    ],
)
def test_validation_rejects_unknown_model_generated_ids(field: str, value: object) -> None:
    registry, page = evidence()
    result = ProfessorResearchResult(
        research_summary="A sufficiently detailed summary grounded in validated research evidence.",
        tags=["Computer Architecture & Hardware"],
        evidence_source_ids=[page.source_id],
    ).model_copy(update={field: value})

    with pytest.raises(ResearchValidationError):
        validate_research_result(
            result,
            pages=[page],
            registry=registry,
        )


def test_validation_rejects_summary_without_identity_matched_page_evidence() -> None:
    registry, page = evidence()
    unverified_page = page.model_copy(update={"identity_signals": IdentitySignals()})
    result = ProfessorResearchResult(
        research_summary="A sufficiently detailed summary that lacks verified identity evidence.",
        tags=["Computer Architecture & Hardware"],
        evidence_source_ids=[page.source_id],
    )

    with pytest.raises(ResearchValidationError, match="identity"):
        validate_research_result(
            result,
            pages=[unverified_page],
            registry=registry,
        )


@pytest.mark.parametrize(
    "tags",
    [
        ["Computer Architecture & Hardware"],
        [
            "Computer Architecture & Hardware",
            "Networking & Mobile Computing",
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
    tags = ["Computer Architecture & Hardware"] * count

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
        "Artificial Intelligence & Machine Learning",
        "Computer Architecture & Systems",
        "computer architecture & systems",
    ],
)
def test_validation_rejects_tags_outside_the_controlled_taxonomy(
    invalid_tag: str,
) -> None:
    registry, page = evidence()
    result = ProfessorResearchResult(
        research_summary="A sufficiently detailed evidence-grounded research summary.",
        tags=[invalid_tag],
        evidence_source_ids=[page.source_id],
    )

    with pytest.raises(ResearchValidationError, match="controlled taxonomy"):
        validate_research_result(
            result,
            pages=[page],
            registry=registry,
        )
