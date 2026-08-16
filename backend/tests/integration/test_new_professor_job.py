import asyncio
import json
import logging
from pathlib import Path

import pytest

from lab_tracker.db.connection import connect_database
from lab_tracker.diagnostics import LOGGER_NAME
from lab_tracker.models.research import OpenAlexPublication, ValidatedProfessorResearch
from lab_tracker.services.discovery import FacultyCandidate
from lab_tracker.services.jobs import JobOutcome, JobRegistry, JobStatus
from lab_tracker.services.update_checks import JobLevelUpdateError, UpdateCheckService


def candidates(count: int = 10) -> list[FacultyCandidate]:
    return [
        FacultyCandidate(
            name=f"Professor {index}",
            title="Assistant Professor",
            email=f"professor-{index}@illinois.edu",
            directory_profile_url=f"https://ece.illinois.edu/about/directory/faculty/{index}",
        )
        for index in range(1, count + 1)
    ]


def research_result(index: int) -> ValidatedProfessorResearch:
    return ValidatedProfessorResearch(
        research_summary=(
            f"Professor {index} studies reliable computing systems and secure hardware design."
        ),
        tags=["Reliable Systems"],
        homepage_url=f"https://professor-{index}.example.edu",
        lab_url=f"https://professor-{index}.example.edu/lab",
        publications=[
            OpenAlexPublication(
                source_id=f"openalex:W{index}",
                openalex_id=f"W{index}",
                title=f"Research Paper {index}",
                year=2026,
                publication_url=f"https://openalex.org/W{index}",
            )
        ],
        source_urls=[f"https://professor-{index}.example.edu"],
        confidence=0.9,
    )


class FakeDiscovery:
    def __init__(self, discovered: list[FacultyCandidate]) -> None:
        self.discovered = discovered
        self.calls = 0

    async def discover(self) -> list[FacultyCandidate]:
        self.calls += 1
        return list(self.discovered)


class FailOnceResearcher:
    def __init__(self, fail_name: str | None = None) -> None:
        self.fail_name = fail_name
        self.failed = False
        self.calls: list[str] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def research(self, candidate: FacultyCandidate) -> ValidatedProfessorResearch:
        self.calls.append(candidate.name)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)
        self.in_flight -= 1
        if candidate.name == self.fail_name and not self.failed:
            self.failed = True
            raise ValueError("candidate-specific research failure")
        index = int(candidate.name.rsplit(" ", 1)[-1])
        return research_result(index)


async def run_job(service: UpdateCheckService):
    job = await service.start_new()
    await service.wait(job.job_id)
    return await service.get_job(job.job_id)


async def professor_count(database_path: Path) -> int:
    with connect_database(database_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM professors").fetchone()[0])


async def application_count(database_path: Path) -> int:
    with connect_database(database_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM application_status").fetchone()[0])


async def publication_count(database_path: Path) -> int:
    with connect_database(database_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM publications").fetchone()[0])


async def proposal_count(database_path: Path) -> int:
    with connect_database(database_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM update_proposals").fetchone()[0])


@pytest.mark.asyncio
async def test_tenth_candidate_failure_keeps_first_nine_and_next_run_retries_only_failure(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "partial-new-job.db"
    discovery = FakeDiscovery(candidates())
    researcher = FailOnceResearcher(fail_name="Professor 10")
    service = UpdateCheckService(
        database_path=database_path,
        jobs=JobRegistry(),
        discovery=discovery,
        researcher=researcher,
    )

    first = await run_job(service)

    assert first.status is JobStatus.COMPLETED
    assert first.outcome is JobOutcome.PARTIAL_SUCCESS
    assert (
        first.discovered_count,
        first.processed_count,
        first.added_count,
        first.failed_count,
    ) == (10, 10, 9, 1)
    assert await professor_count(database_path) == 9
    assert await publication_count(database_path) == 9
    assert await application_count(database_path) == 0
    assert await proposal_count(database_path) == 0
    assert researcher.max_in_flight == 1

    researcher.calls.clear()
    second = await run_job(service)

    assert second.status is JobStatus.COMPLETED
    assert second.outcome is JobOutcome.SUCCESS
    assert (second.discovered_count, second.added_count, second.failed_count) == (1, 1, 0)
    assert researcher.calls == ["Professor 10"]
    assert await professor_count(database_path) == 10
    assert await publication_count(database_path) == 10

    await service.shutdown()


class JobLevelFailingResearcher(FailOnceResearcher):
    async def research(self, candidate: FacultyCandidate) -> ValidatedProfessorResearch:
        if candidate.name == "Professor 3":
            self.calls.append(candidate.name)
            raise JobLevelUpdateError("PROVIDER_QUOTA_EXHAUSTED", "Provider quota exhausted")
        return await super().research(candidate)


@pytest.mark.asyncio
async def test_job_level_failure_stops_remaining_candidates_but_keeps_prior_commits(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "job-level-failure.db"
    researcher = JobLevelFailingResearcher()
    service = UpdateCheckService(
        database_path=database_path,
        jobs=JobRegistry(),
        discovery=FakeDiscovery(candidates()),
        researcher=researcher,
    )

    job = await run_job(service)

    assert job.status is JobStatus.FAILED
    assert job.error_code == "PROVIDER_QUOTA_EXHAUSTED"
    assert (job.discovered_count, job.processed_count, job.added_count, job.failed_count) == (
        10,
        3,
        2,
        1,
    )
    assert researcher.calls == ["Professor 1", "Professor 2", "Professor 3"]
    assert await professor_count(database_path) == 2

    await service.shutdown()


@pytest.mark.asyncio
async def test_new_job_logs_validated_professor_before_persistence(
    tmp_path: Path,
    caplog,
) -> None:
    database_path = tmp_path / "logged-new-job.db"
    service = UpdateCheckService(
        database_path=database_path,
        jobs=JobRegistry(),
        discovery=FakeDiscovery(candidates(1)),
        researcher=FailOnceResearcher(),
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        job = await run_job(service)

    message = next(
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("professor.extracted ")
    )
    payload = json.loads(message.split(" ", 1)[1])
    assert job.status is JobStatus.COMPLETED
    assert payload["name"] == "Professor 1"
    assert payload["lab_url"] == "https://professor-1.example.edu/lab"
    assert payload["publications"][0]["title"] == "Research Paper 1"
    assert await professor_count(database_path) == 1

    await service.shutdown()
