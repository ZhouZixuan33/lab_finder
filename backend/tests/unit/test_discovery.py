from pathlib import Path

import pytest

from lab_tracker.services.discovery import (
    FacultyCandidate,
    enrich_candidate_from_profile,
    is_research_active_title,
    parse_faculty_directory,
    research_new_candidates,
)
from lab_tracker.services.identity import ExistingProfessorIdentity, IdentityIndex

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_directory_parser_extracts_identity_and_filters_research_active_titles() -> None:
    html = (FIXTURES / "uiuc_faculty_directory.html").read_text(encoding="utf-8")
    candidates = parse_faculty_directory(html)

    assert [(item.name, item.title, item.email) for item in candidates] == [
        ("Alice Systems", "Assistant Professor", "alice@illinois.edu"),
        ("Bob Teacher", "Teaching Associate Professor", "bob@illinois.edu"),
        ("Carol Researcher", "Research Professor", None),
        ("Dana Administrator", "Department Head, Electrical & Computer Engineering", None),
    ]
    assert is_research_active_title(candidates[0].title) is True
    assert is_research_active_title(candidates[1].title) is False
    assert is_research_active_title(candidates[2].title) is True
    assert is_research_active_title(candidates[3].title) is None


def test_profile_enrichment_fills_email_and_detects_research_evidence() -> None:
    html = (FIXTURES / "uiuc_faculty_profile.html").read_text(encoding="utf-8")
    enriched = enrich_candidate_from_profile(
        FacultyCandidate(
            name="Carol Researcher",
            title="Research Professor",
            email=None,
            directory_profile_url="https://ece.illinois.edu/about/directory/faculty/carol",
        ),
        html,
    )

    assert enriched.email == "carol@illinois.edu"
    assert enriched.has_research_evidence is True


@pytest.mark.asyncio
async def test_scope_new_skips_existing_before_research_and_continues_after_ambiguity() -> None:
    candidates = [
        FacultyCandidate(
            name="Existing Person",
            title="Professor",
            email="existing@illinois.edu",
            directory_profile_url="https://ece.illinois.edu/existing",
        ),
        FacultyCandidate(
            name="Ambiguous Person",
            title="Professor",
            email="shared@illinois.edu",
            directory_profile_url="https://ece.illinois.edu/ambiguous",
        ),
        FacultyCandidate(
            name="New Person",
            title="Assistant Professor",
            email="new@illinois.edu",
            directory_profile_url="https://ece.illinois.edu/new",
        ),
    ]
    identities = IdentityIndex(
        [
            ExistingProfessorIdentity(
                professor_id=1,
                name="Existing Person",
                email="existing@illinois.edu",
                directory_profile_url="https://ece.illinois.edu/existing",
            ),
            ExistingProfessorIdentity(
                professor_id=2,
                name="First Shared",
                email="shared@illinois.edu",
                directory_profile_url="https://ece.illinois.edu/first",
            ),
            ExistingProfessorIdentity(
                professor_id=3,
                name="Second Shared",
                email="shared@illinois.edu",
                directory_profile_url="https://ece.illinois.edu/second",
            ),
        ]
    )
    researched: list[str] = []

    async def research_provider(item: FacultyCandidate) -> str:
        researched.append(item.name)
        return f"researched:{item.name}"

    result = await research_new_candidates(candidates, identities, research_provider)

    assert researched == ["New Person"]
    assert result.results == ["researched:New Person"]
    assert result.existing_count == 1
    assert [failure.candidate.name for failure in result.failures] == ["Ambiguous Person"]
