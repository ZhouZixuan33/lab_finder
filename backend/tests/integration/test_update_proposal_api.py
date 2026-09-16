import logging
import time
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from lab_tracker.config import Settings
from lab_tracker.db.connection import connect_database
from lab_tracker.db.migrations import run_migrations
from lab_tracker.diagnostics import LOGGER_NAME
from lab_tracker.main import create_app
from lab_tracker.models.application import ApplicationUpsert
from lab_tracker.models.common import ApplicationState, ProposalStatus
from lab_tracker.models.professor import ProfessorCreate
from lab_tracker.models.publication import PublicationCreate
from lab_tracker.models.research import (
    OpenAlexPublication,
    ResearchIdentity,
    ValidatedProfessorResearch,
)
from lab_tracker.models.update import ProposalCreate
from lab_tracker.repositories.applications import ApplicationsRepository
from lab_tracker.repositories.professors import ProfessorsRepository
from lab_tracker.repositories.proposals import ProposalsRepository
from lab_tracker.repositories.publications import PublicationsRepository
from lab_tracker.services.diff import ProfessorUpdateSnapshot, PublicationDifference
from lab_tracker.services.discovery import FacultyCandidate
from lab_tracker.services.jobs import JobRegistry
from lab_tracker.services.update_checks import UpdateCheckService, _PublicationLookup
from lab_tracker.services.updates import ProfessorUpdateService

NOW = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)


class EmptyDiscovery:
    async def discover(self) -> list[FacultyCandidate]:
        return []


class RefreshResearcher:
    def __init__(self, result: ValidatedProfessorResearch) -> None:
        self.result = result
        self.normal_calls = 0
        self.refresh_calls = 0

    async def research(self, _candidate: FacultyCandidate) -> ValidatedProfessorResearch:
        self.normal_calls += 1
        return self.result

    async def research_with_refresh(
        self,
        _candidate: FacultyCandidate,
    ) -> ValidatedProfessorResearch:
        self.refresh_calls += 1
        return self.result


def runtime_settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=database_path,
        llm_api_key="test-llm-key",
        llm_model="test-model",
        tavily_api_key="test-tavily-key",
        openalex_api_key="test-openalex-key",
    )


def seed_professor(database_path: Path) -> int:
    with connect_database(database_path) as connection:
        run_migrations(connection)
        professor = ProfessorsRepository(connection).create(
            ProfessorCreate(
                name="Alice Systems",
                title="Professor",
                email="alice@illinois.edu",
                official_profile_url="https://ece.illinois.edu/alice",
                personal_homepage_url="https://alice.example.edu/lab",
                research_summary=(
                    "Alice studies reliable computer architecture and secure accelerators."
                ),
                tags=["Architecture"],
                source_urls=["https://ece.illinois.edu/alice"],
                source_hash="old-hash",
            ),
            now=NOW,
        )
        PublicationsRepository(connection).create_many(
            professor.id,
            [
                PublicationCreate(
                    title="Old Paper",
                    year=2025,
                    source="openalex",
                )
            ],
            now=NOW,
        )
        ApplicationsRepository(connection).upsert(
            professor.id,
            ApplicationUpsert(
                state=ApplicationState.APPLIED,
                application_date=date(2026, 8, 15),
                notes="Application submitted.",
            ),
            now=NOW,
        )
        return professor.id


def changed_research() -> ValidatedProfessorResearch:
    return ValidatedProfessorResearch(
        research_summary=(
            "Alice studies dependable AI accelerators and fault-tolerant computer systems."
        ),
        tags=["Reliable AI", "Computer Architecture"],
        personal_homepage_url="https://alice.example.edu/new-lab",
        publications=[
            OpenAlexPublication(
                source_id="openalex:W2",
                openalex_id="W2",
                title="Dependable AI Hardware",
                year=2026,
                publication_url="https://openalex.org/W2",
            )
        ],
        source_urls=["https://alice.example.edu", "https://alice.example.edu/new-lab"],
        confidence=0.92,
    )


def build_client(
    database_path: Path,
    research: ValidatedProfessorResearch,
) -> tuple[TestClient, RefreshResearcher, int]:
    professor_id = seed_professor(database_path)
    researcher = RefreshResearcher(research)
    professor_updates = ProfessorUpdateService(database_path, researcher)
    checks = UpdateCheckService(
        database_path=database_path,
        jobs=JobRegistry(),
        discovery=EmptyDiscovery(),
        researcher=researcher,
        professor_updates=professor_updates,
    )
    app = create_app(
        settings=runtime_settings(database_path),
        update_check_service=checks,
    )
    return TestClient(app), researcher, professor_id


def wait_for_job(client: TestClient, job_id: str) -> dict[str, object]:
    for _attempt in range(100):
        payload = client.get(f"/api/update-checks/{job_id}").json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("Update job did not finish")


def test_publication_failure_still_returns_reviewable_and_applicable_update(tmp_path: Path):
    research = changed_research().model_copy(update={
        "prospective_students_quote": "Prospective students are welcome to apply.",
        "prospective_students_source_url": "https://alice.example.edu",
    })
    client, researcher, professor_id = build_client(tmp_path / "publication-failure.db", research)

    class FailingOpenAlex:
        async def get_recent_publications(self, identity):
            raise httpx.ReadTimeout("OpenAlex unavailable")

    async def refresh(candidate):
        lookup = _PublicationLookup(FailingOpenAlex())
        papers = await lookup.get_recent_publications(ResearchIdentity(
            name=candidate.name, title=candidate.title, affiliation=candidate.affiliation,
            official_profile_url=candidate.official_profile_url,
        ))
        return research.model_copy(update={
            "publications": papers, "publications_unavailable": lookup.unavailable,
        })

    researcher.research_with_refresh = refresh
    with client:
        before = client.get(f"/api/professors/{professor_id}").json()
        started = client.post("/api/update-checks", json={
            "scope": "professor", "professor_id": professor_id,
        })
        completed = wait_for_job(client, started.json()["job_id"])
        assert completed["status"] == "completed"
        assert completed["changed"] is True
        proposal_id = completed["proposal_id"]
        proposal = client.get(f"/api/update-proposals/{proposal_id}").json()
        assert proposal["new_values"]["research_summary"] == research.research_summary
        assert proposal["publication_diff"]["removed"] == []
        assert proposal["publication_diff"]["added"] == []
        assert client.post(f"/api/update-proposals/{proposal_id}/apply").status_code == 200
        after = client.get(f"/api/professors/{professor_id}").json()
        assert after["research_summary"] == research.research_summary
        assert after["tags"] == research.tags
        assert after["prospective_students_quote"] == research.prospective_students_quote
        assert [p["title"] for p in after["publications"]] == [
            p["title"] for p in before["publications"]
        ]
        assert after["application"] == before["application"]


def test_single_check_creates_pending_without_writes_then_apply_is_atomic(
    tmp_path: Path,
    caplog,
) -> None:
    database_path = tmp_path / "proposal-apply.db"
    client, researcher, professor_id = build_client(database_path, changed_research())

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME), client:
        started = client.post(
            "/api/update-checks",
            json={"scope": "professor", "professor_id": professor_id},
        )
        completed = wait_for_job(client, started.json()["job_id"])
        proposal_id = completed["proposal_id"]
        detail_before = client.get(f"/api/professors/{professor_id}").json()
        pending_list = client.get(
            "/api/update-proposals",
            params={"status": "pending", "professor_id": professor_id},
        )
        conflict = client.post(
            "/api/update-checks",
            json={"scope": "professor", "professor_id": professor_id},
        )
        proposal = client.get(f"/api/update-proposals/{proposal_id}")
        applied = client.post(f"/api/update-proposals/{proposal_id}/apply")
        repeated = client.post(f"/api/update-proposals/{proposal_id}/apply")
        detail_after = client.get(f"/api/professors/{professor_id}").json()

    assert started.status_code == 202
    assert completed["status"] == "completed"
    assert completed["changed"] is True
    assert researcher.refresh_calls == 1
    assert researcher.normal_calls == 0
    assert detail_before["research_summary"].startswith("Alice studies reliable")
    assert detail_before["application"]["state"] == "applied"
    assert pending_list.status_code == 200
    assert pending_list.json()["pagination"]["total"] == 1
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "PENDING_UPDATE_EXISTS"
    assert conflict.json()["error"]["details"]["proposal_id"] == proposal_id
    assert proposal.json()["new_values"]["personal_homepage_url"].endswith("/new-lab")
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "PROPOSAL_NOT_PENDING"
    assert detail_after["research_summary"].startswith("Alice studies dependable")
    assert [item["title"] for item in detail_after["publications"]] == [
        "Dependable AI Hardware"
    ]
    assert detail_after["application"] == detail_before["application"]
    assert any(
        record.getMessage().startswith("professor.extracted ")
        and '"name":"Alice Systems"' in record.getMessage()
        for record in caplog.records
    )


def test_missing_author_preserves_publications_when_homepage_proposal_is_applied(tmp_path: Path):
    research = changed_research().model_copy(update={
        "publications": [], "publications_unavailable": True,
        "personal_homepage_url": "https://alice.github.io/",
    })
    client, _, professor_id = build_client(tmp_path / "missing-author.db", research)
    with client:
        before = client.get(f"/api/professors/{professor_id}").json()
        started = client.post(
            "/api/update-checks", json={"scope": "professor", "professor_id": professor_id},
        )
        completed = wait_for_job(client, started.json()["job_id"])
        assert completed["status"] == "completed"
        proposal_id = completed["proposal_id"]
        proposal = client.get(f"/api/update-proposals/{proposal_id}").json()
        assert proposal["publication_diff"]["removed"] == []
        assert proposal["publication_diff"]["added"] == []
        assert proposal["publication_diff"]["proposed"][0]["title"] == "Old Paper"
        assert client.post(f"/api/update-proposals/{proposal_id}/apply").status_code == 200
        after = client.get(f"/api/professors/{professor_id}").json()
    assert after["personal_homepage_url"] == "https://alice.github.io/"
    assert [p["title"] for p in after["publications"]] == [
        p["title"] for p in before["publications"]
    ]


@pytest.mark.parametrize("failure_stage", ["publication_insert", "mark_applied"])
def test_apply_late_failure_restores_professor_papers_and_pending_status(
    tmp_path: Path, monkeypatch, failure_stage: str,
) -> None:
    client, _, professor_id = build_client(tmp_path / "late-rollback.db", changed_research())
    checkpoints = []
    with client:
        started = client.post(
            "/api/update-checks", json={"scope": "professor", "professor_id": professor_id},
        )
        proposal_id = wait_for_job(client, started.json()["job_id"])["proposal_id"]
        before = client.get(f"/api/professors/{professor_id}").json()

        def fail(repository, *args, **kwargs):
            # The professor update has already happened, and the old papers have
            # already been deleted. Rollback must undo those successful writes.
            current = ProfessorsRepository(repository.connection).get(professor_id)
            papers = PublicationsRepository(repository.connection).list_for_professor(professor_id)
            checkpoints.append((
                repository.connection.in_transaction,
                current.research_summary,
                [paper.title for paper in papers],
            ))
            raise RuntimeError("Injected late transaction failure")

        if failure_stage == "publication_insert":
            monkeypatch.setattr(PublicationsRepository, "create_many", fail)
        else:
            monkeypatch.setattr(ProposalsRepository, "mark_applied", fail)
        response = client.post(f"/api/update-proposals/{proposal_id}/apply")
        after = client.get(f"/api/professors/{professor_id}").json()
        proposal = client.get(f"/api/update-proposals/{proposal_id}").json()

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "PROPOSAL_APPLY_FAILED"
    assert len(checkpoints) == 1
    in_transaction, summary, titles = checkpoints[0]
    assert in_transaction
    assert summary.startswith("Alice studies dependable")
    assert titles == ([] if failure_stage == "publication_insert" else ["Dependable AI Hardware"])
    assert after == before
    assert proposal["status"] == "pending"


def test_no_difference_returns_changed_false_and_reject_is_one_way(tmp_path: Path) -> None:
    database_path = tmp_path / "proposal-no-change.db"
    unchanged = ValidatedProfessorResearch(
        research_summary="Alice studies reliable computer architecture and secure accelerators.",
        tags=["Architecture"],
        personal_homepage_url="https://alice.example.edu/lab",
        publications=[
            OpenAlexPublication(
                source_id="openalex:W1",
                openalex_id="W1",
                title="Old Paper",
                year=2025,
            )
        ],
        source_urls=["https://ece.illinois.edu/alice"],
    )
    client, researcher, professor_id = build_client(database_path, unchanged)

    with client:
        started = client.post(
            "/api/update-checks",
            json={"scope": "professor", "professor_id": professor_id},
        )
        completed = wait_for_job(client, started.json()["job_id"])
        proposals = client.get(
            "/api/update-proposals",
            params={"professor_id": professor_id},
        ).json()

    assert completed["changed"] is False
    assert completed["proposal_id"] is None
    assert proposals["pagination"]["total"] == 0
    assert researcher.refresh_calls == 1


def test_reject_marks_pending_and_cannot_be_repeated(tmp_path: Path) -> None:
    database_path = tmp_path / "proposal-reject.db"
    client, _researcher, professor_id = build_client(database_path, changed_research())

    with client:
        started = client.post(
            "/api/update-checks",
            json={"scope": "professor", "professor_id": professor_id},
        )
        proposal_id = wait_for_job(client, started.json()["job_id"])["proposal_id"]
        rejected = client.post(f"/api/update-proposals/{proposal_id}/reject")
        repeated = client.post(f"/api/update-proposals/{proposal_id}/reject")
        detail = client.get(f"/api/professors/{professor_id}").json()

    assert rejected.status_code == 200
    assert rejected.json()["status"] == ProposalStatus.REJECTED
    assert repeated.status_code == 409
    assert detail["research_summary"].startswith("Alice studies reliable")
    assert detail["application"]["notes"] == "Application submitted."


def test_apply_constraint_failure_rolls_back_and_keeps_proposal_pending(tmp_path: Path) -> None:
    database_path = tmp_path / "proposal-rollback.db"
    client, _researcher, professor_id = build_client(database_path, changed_research())

    with connect_database(database_path) as connection:
        second = ProfessorsRepository(connection).create(
            ProfessorCreate(
                name="Bob Circuits",
                title="Professor",
                official_profile_url="https://ece.illinois.edu/bob",
                research_summary="Bob studies integrated circuits and electronic systems.",
                source_hash="bob-hash",
            ),
            now=NOW,
        )
        current = ProfessorsRepository(connection).get(professor_id)
        assert current is not None
        old_values = ProfessorUpdateSnapshot(
            name=current.name,
            title=current.title,
            email=current.email,
            official_profile_url=current.official_profile_url,
            personal_homepage_url=current.personal_homepage_url,
            research_summary=current.research_summary,
            tags=current.tags,
            source_urls=current.source_urls,
            source_hash=current.source_hash,
        )
        new_values = old_values.model_copy(
            update={
                "official_profile_url": second.official_profile_url,
                "research_summary": "This write must roll back because the URL is duplicated.",
                "source_hash": "conflicting-hash",
            }
        )
        proposal = ProposalsRepository(connection).create_pending(
            ProposalCreate(
                job_id="rollback-job",
                professor_id=professor_id,
                old_values=old_values.model_dump(mode="json"),
                new_values=new_values.model_dump(mode="json"),
                publication_diff=PublicationDifference(proposed=[]).model_dump(mode="json"),
                source_urls=new_values.source_urls,
            ),
            now=NOW,
        )

    with client:
        failed = client.post(f"/api/update-proposals/{proposal.id}/apply")
        missing = client.get("/api/update-proposals/99999")

    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "PROPOSAL_APPLY_FAILED"
    assert missing.status_code == 404
    with connect_database(database_path) as connection:
        current_after = ProfessorsRepository(connection).get(professor_id)
        pending_after = ProposalsRepository(connection).get(proposal.id)
        publications_after = PublicationsRepository(connection).list_for_professor(professor_id)
        application_after = ApplicationsRepository(connection).get(professor_id)
    assert current_after is not None
    assert current_after.official_profile_url == "https://ece.illinois.edu/alice"
    assert current_after.research_summary.startswith("Alice studies reliable")
    assert pending_after is not None and pending_after.status is ProposalStatus.PENDING
    assert [item.title for item in publications_after] == ["Old Paper"]
    assert application_after is not None and application_after.state is ApplicationState.APPLIED
