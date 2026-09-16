import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from lab_tracker.db.connection import connect_database
from lab_tracker.db.migrations import run_migrations
from lab_tracker.models.application import ApplicationUpsert
from lab_tracker.models.common import ApplicationState, ProposalStatus
from lab_tracker.models.professor import ProfessorCreate
from lab_tracker.models.publication import PublicationCreate
from lab_tracker.models.update import ProposalCreate
from lab_tracker.repositories.applications import ApplicationsRepository
from lab_tracker.repositories.professors import ProfessorsRepository
from lab_tracker.repositories.proposals import ProposalsRepository
from lab_tracker.repositories.publications import PublicationsRepository

NOW = datetime(2026, 8, 16, 8, 30, tzinfo=UTC)


@contextmanager
def repositories(
    database_path: Path,
) -> Iterator[
    tuple[
        sqlite3.Connection,
        ProfessorsRepository,
        ApplicationsRepository,
        PublicationsRepository,
        ProposalsRepository,
    ]
]:
    with connect_database(database_path) as connection:
        run_migrations(connection)
        yield (
            connection,
            ProfessorsRepository(connection),
            ApplicationsRepository(connection),
            PublicationsRepository(connection),
            ProposalsRepository(connection),
        )


def professor_input(
    name: str,
    *,
    title: str = "Professor",
    email: str | None = None,
    tags: list[str] | None = None,
) -> ProfessorCreate:
    slug = name.lower().replace(" ", "-")
    return ProfessorCreate(
        name=name,
        title=title,
        email=email,
        official_profile_url=f"https://ece.illinois.edu/{slug}",
        personal_homepage_url=f"https://example.edu/{slug}/lab",
        research_summary=f"{name} researches reliable computing.",
        tags=tags or [],
        source_urls=[f"https://ece.illinois.edu/{slug}"],
        source_hash=f"hash-{slug}",
    )


def test_professor_list_search_filters_paginates_and_preserves_untracked_rows(
    tmp_path: Path,
) -> None:
    with repositories(tmp_path / "list.db") as (
        connection,
        professors,
        applications,
        _publications,
        _proposals,
    ):
        alice = professors.create(
            professor_input(
                "Alice Systems",
                email="alice@illinois.edu",
                tags=["Computer Architecture", "Reliable AI"],
            ),
            now=NOW,
        )
        bob = professors.create(
            professor_input("Bob Circuits", tags=["Integrated Circuits"]),
            now=NOW,
        )
        professors.create(
            professor_input("Carol Vision", tags=["Reliable AI", "Imaging"]),
            now=NOW,
        )
        applications.upsert(
            alice.id,
            ApplicationUpsert(state=ApplicationState.INTERESTED),
            now=NOW,
        )
        applications.upsert(
            bob.id,
            ApplicationUpsert(state=ApplicationState.APPLIED),
            now=NOW,
        )

        all_items, all_total = professors.list(page=1, page_size=10)
        search_items, search_total = professors.list(search="architecture")
        tag_items, tag_total = professors.list(tags=["reliable ai"])
        state_items, state_total = professors.list(state=ApplicationState.APPLIED)
        second_page, paged_total = professors.list(
            page=2,
            page_size=1,
            sort="name",
            order="desc",
        )

        assert all_total == 3
        assert {item.name for item in all_items} == {
            "Alice Systems",
            "Bob Circuits",
            "Carol Vision",
        }
        carol = next(item for item in all_items if item.name == "Carol Vision")
        assert carol.application_state is None
        assert [item.name for item in search_items] == ["Alice Systems"]
        assert search_total == 1
        assert {item.name for item in tag_items} == {"Alice Systems", "Carol Vision"}
        assert tag_total == 2
        assert [item.name for item in state_items] == ["Bob Circuits"]
        assert state_total == 1
        assert [item.name for item in second_page] == ["Bob Circuits"]
        assert paged_total == 3

        injected_items, injected_total = professors.list(search="%' OR 1=1 --")
        assert injected_items == []
        assert injected_total == 0
        injected_tag_items, injected_tag_total = professors.list(
            tags=["reliable ai') OR 1=1 --"]
        )
        assert injected_tag_items == []
        assert injected_tag_total == 0
        assert connection.execute("SELECT COUNT(*) FROM professors").fetchone()[0] == 3

        with pytest.raises(ValueError):
            professors.list(sort="name; DROP TABLE professors")
        with pytest.raises(ValueError):
            professors.list(order="desc; DROP TABLE professors")
        with pytest.raises(ValueError):
            professors.list(state="not_tracked")


def test_professor_detail_and_tag_aggregation_include_related_records(tmp_path: Path) -> None:
    with repositories(tmp_path / "detail.db") as (
        _connection,
        professors,
        applications,
        publications,
        proposals,
    ):
        professor = professors.create(
            professor_input("Alice Systems", tags=["Reliable AI", "Architecture"]),
            now=NOW,
        )
        applications.upsert(
            professor.id,
            ApplicationUpsert(
                state=ApplicationState.APPLIED,
                application_date=date(2026, 8, 15),
                notes="Portal submitted.",
            ),
            now=NOW,
        )
        publications.create_many(
            professor.id,
            [
                PublicationCreate(
                    title="Reliable Accelerators",
                    year=2026,
                    venue="ExampleConf",
                    source="openalex",
                )
            ],
            now=NOW,
        )
        proposal = proposals.create_pending(
            ProposalCreate(
                job_id="job-detail",
                professor_id=professor.id,
                old_values={"title": "Professor"},
                new_values={"title": "Professor and Chair"},
                publication_diff={"added": [], "removed": []},
                source_urls=[professor.official_profile_url],
                confidence=0.9,
            ),
            now=NOW,
        )

        detail = professors.get_detail(professor.id)
        tags = professors.list_tags()

    assert detail is not None
    assert detail.application is not None
    assert detail.application.state is ApplicationState.APPLIED
    assert [publication.title for publication in detail.publications] == [
        "Reliable Accelerators"
    ]
    assert detail.pending_proposal_id == proposal.id
    assert {(tag.tag, tag.professor_count) for tag in tags} == {
        ("architecture", 1),
        ("reliable ai", 1),
    }


def test_application_upsert_and_delete_never_remove_the_professor(tmp_path: Path) -> None:
    with repositories(tmp_path / "application.db") as (
        connection,
        professors,
        applications,
        _publications,
        _proposals,
    ):
        professor = professors.create(professor_input("Alice Systems"), now=NOW)

        applications.upsert(
            professor.id,
            ApplicationUpsert(state=ApplicationState.INTERESTED, notes="Drafting email."),
            now=NOW,
        )
        updated = applications.upsert(
            professor.id,
            ApplicationUpsert(
                state=ApplicationState.APPLIED,
                application_date=date(2026, 8, 16),
                notes="Sent.",
            ),
            now=NOW,
        )
        deleted = applications.delete(professor.id)

        assert updated.state is ApplicationState.APPLIED
        assert applications.get(professor.id) is None
        assert deleted is True
        assert connection.execute(
            "SELECT COUNT(*) FROM professors WHERE id = ?", (professor.id,)
        ).fetchone()[0] == 1


def test_proposal_repository_enforces_pending_and_one_way_resolution(tmp_path: Path) -> None:
    with repositories(tmp_path / "proposal.db") as (
        _connection,
        professors,
        _applications,
        _publications,
        proposals,
    ):
        professor = professors.create(professor_input("Alice Systems"), now=NOW)
        candidate = ProposalCreate(
            job_id="job-one",
            professor_id=professor.id,
            old_values={"title": "Professor"},
            new_values={"title": "Professor and Chair"},
            publication_diff={"added": [], "removed": []},
            confidence=0.9,
        )
        proposal = proposals.create_pending(candidate, now=NOW)

        assert proposals.get_pending_for_professor(professor.id) == proposal
        with pytest.raises(sqlite3.IntegrityError):
            proposals.create_pending(
                candidate.model_copy(update={"job_id": "job-two"}),
                now=NOW,
            )

        resolved = proposals.mark_rejected(proposal.id, resolved_at=NOW)
        repeated = proposals.mark_applied(proposal.id, resolved_at=NOW)

    assert resolved is not None
    assert resolved.status is ProposalStatus.REJECTED
    assert repeated is None
