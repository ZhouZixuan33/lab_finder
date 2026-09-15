import pytest

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

QUOTE = "Prospective students are welcome to contact me to join my group."


@pytest.mark.parametrize("mode", ["yes", "absent", "fabricated", "missing_id", "unknown_id"])
def test_prospective_students_requires_cited_verbatim_evidence(mode):
    registry = CandidateSourceRegistry()
    source = registry.register_hit(SearchHit(title="Alice", url="https://alice.example.edu"))
    page = ExtractedPage(
        source_id=source.source_id,
        candidate_id=source.candidate_id,
        url=source.url,
        text="Alice researches computer architecture. " + QUOTE,
        identity_signals=IdentitySignals(name_match=True),
    )
    result = ProfessorResearchResult(
        research_summary="Alice researches computer architecture and reliable computing systems.",
        tags=["Computer Architecture & Hardware"],
        evidence_source_ids=[source.source_id],
        prospective_students_quote=None if mode == "absent" else (
            "Invented invitation." if mode == "fabricated" else QUOTE
        ),
        prospective_students_source_id=None if mode in {"absent", "missing_id"} else (
            "source_missing" if mode == "unknown_id" else source.source_id
        ),
    )
    if mode in {"fabricated", "missing_id", "unknown_id"}:
        with pytest.raises(ResearchValidationError):
            validate_research_result(result, pages=[page], registry=registry)
    else:
        validated = validate_research_result(result, pages=[page], registry=registry)
        assert validated.prospective_students_quote == (QUOTE if mode == "yes" else None)
        assert validated.prospective_students_source_url == (source.url if mode == "yes" else None)
