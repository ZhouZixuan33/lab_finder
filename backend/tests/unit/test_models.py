from datetime import date

import pytest
from pydantic import ValidationError

from lab_tracker.models.application import ApplicationUpsert
from lab_tracker.models.common import ApplicationState, ProposalStatus
from lab_tracker.models.professor import ProfessorCreate
from lab_tracker.models.update import ProposalCreate


def test_application_model_allows_only_the_four_confirmed_states() -> None:
    application = ApplicationUpsert(
        state=ApplicationState.APPLIED,
        application_date=date(2026, 8, 16),
        notes="Sent through the department portal.",
    )

    assert application.state is ApplicationState.APPLIED

    with pytest.raises(ValidationError):
        ApplicationUpsert(state="not_tracked")


def test_professor_storage_model_accepts_legacy_free_form_tags() -> None:
    professor = ProfessorCreate(
        name="Jane Example",
        title="Professor",
        email="jane@example.edu",
        official_profile_url="https://ece.illinois.edu/example",
        research_summary="Works on useful systems.",
        tags=["Never Seen Before", "AI + Hardware"],
        source_urls=["https://ece.illinois.edu/example"],
        source_hash="hash",
    )

    assert professor.tags == ["Never Seen Before", "AI + Hardware"]


def test_proposal_model_rejects_removed_status_and_invalid_confidence() -> None:
    proposal = ProposalCreate(
        job_id="7bb47865-fda5-4f64-b82b-b84f206e87a2",
        professor_id=1,
        old_values={"title": "Professor"},
        new_values={"title": "Associate Professor"},
        publication_diff={"added": [], "removed": []},
        source_urls=["https://ece.illinois.edu/example"],
        confidence=0.8,
    )

    assert proposal.confidence == 0.8
    assert set(ProposalStatus) == {
        ProposalStatus.PENDING,
        ProposalStatus.APPLIED,
        ProposalStatus.REJECTED,
    }

    with pytest.raises(ValidationError):
        ProposalCreate(
            job_id="job",
            professor_id=1,
            old_values={},
            new_values={},
            publication_diff={},
            confidence=1.1,
        )
