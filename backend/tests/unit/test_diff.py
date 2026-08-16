from datetime import UTC, datetime

from lab_tracker.models.professor import ProfessorRecord
from lab_tracker.models.publication import PublicationRecord
from lab_tracker.models.research import OpenAlexPublication, ValidatedProfessorResearch
from lab_tracker.services.diff import compare_professor_update

NOW = datetime(2026, 8, 16, tzinfo=UTC)


def current_professor() -> ProfessorRecord:
    return ProfessorRecord(
        id=1,
        name="Alice Systems",
        title="Professor",
        email="alice@illinois.edu",
        directory_profile_url="https://ece.illinois.edu/alice",
        homepage_url="https://alice.example.edu",
        lab_url="https://alice.example.edu/lab",
        research_summary="Alice studies reliable computer architecture and secure accelerators.",
        tags=["Architecture", "Reliable AI"],
        source_urls=["https://ece.illinois.edu/alice", "https://alice.example.edu"],
        source_hash="old-hash",
        created_at=NOW,
        last_checked_at=NOW,
        updated_at=NOW,
    )


def current_publication() -> PublicationRecord:
    return PublicationRecord(
        id=1,
        professor_id=1,
        title="Reliable Accelerators",
        year=2026,
        venue="ExampleConf",
        publication_url="https://openalex.org/W1",
        doi="10.1000/example",
        source="openalex",
        created_at=NOW,
    )


def same_research() -> ValidatedProfessorResearch:
    return ValidatedProfessorResearch(
        research_summary="Alice studies reliable computer architecture and secure accelerators.",
        tags=["Reliable AI", "Architecture"],
        homepage_url="https://alice.example.edu",
        lab_url="https://alice.example.edu/lab",
        publications=[
            OpenAlexPublication(
                source_id="openalex:W1",
                openalex_id="W1",
                title="Reliable Accelerators",
                year=2026,
                venue="ExampleConf",
                publication_url="https://openalex.org/W1",
                doi="10.1000/example",
            )
        ],
        source_urls=["https://alice.example.edu", "https://ece.illinois.edu/alice"],
        confidence=0.9,
    )


def test_reordered_tags_sources_and_publications_are_not_real_differences() -> None:
    difference = compare_professor_update(
        current_professor(),
        [current_publication()],
        same_research(),
    )

    assert difference.changed is False
    assert difference.field_changes == {}
    assert difference.publication_diff.added == []
    assert difference.publication_diff.removed == []


def test_changed_summary_and_publications_produce_complete_apply_snapshot() -> None:
    research = same_research().model_copy(
        update={
            "research_summary": (
                "Alice studies dependable AI accelerators and fault-tolerant computer systems."
            ),
            "publications": [
                OpenAlexPublication(
                    source_id="openalex:W2",
                    openalex_id="W2",
                    title="Dependable AI Hardware",
                    year=2026,
                )
            ],
        }
    )

    difference = compare_professor_update(
        current_professor(),
        [current_publication()],
        research,
    )

    assert difference.changed is True
    assert difference.field_changes["research_summary"]["old"].startswith("Alice studies reliable")
    new_summary = difference.field_changes["research_summary"]["new"]
    assert new_summary.startswith("Alice studies dependable")
    assert [item.title for item in difference.publication_diff.added] == [
        "Dependable AI Hardware"
    ]
    assert [item.title for item in difference.publication_diff.removed] == [
        "Reliable Accelerators"
    ]
    assert [item.title for item in difference.publication_diff.proposed] == [
        "Dependable AI Hardware"
    ]
    assert difference.new_values.source_hash != "old-hash"
