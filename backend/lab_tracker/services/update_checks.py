"""Background orchestration for resilient professor update checks."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from langchain_openai import ChatOpenAI

from lab_tracker.config import Settings
from lab_tracker.db.connection import connect_database, transaction
from lab_tracker.db.migrations import run_migrations
from lab_tracker.models.professor import ProfessorCreate
from lab_tracker.models.publication import PublicationCreate
from lab_tracker.models.research import (
    ResearchIdentity,
    SearchHit,
    ValidatedProfessorResearch,
)
from lab_tracker.repositories.professors import ProfessorsRepository
from lab_tracker.repositories.publications import PublicationsRepository
from lab_tracker.services.discovery import FacultyCandidate, FacultyDiscoveryClient
from lab_tracker.services.http import RateLimitedHttpClient
from lab_tracker.services.identity import (
    AmbiguousIdentityError,
    ExistingProfessorIdentity,
    IdentityIndex,
)
from lab_tracker.services.jobs import JobRegistry, JobScope, JobSnapshot
from lab_tracker.services.openalex_provider import OpenAlexProvider
from lab_tracker.services.page_extractor import PageExtractor
from lab_tracker.services.rate_limit import SerialRateLimiter
from lab_tracker.services.research_graph import ProfessorResearchGraph
from lab_tracker.services.research_sources import CandidateSourceRegistry
from lab_tracker.services.research_tools import create_research_tools
from lab_tracker.services.tavily_provider import TavilyProvider
from lab_tracker.services.updates import (
    PendingUpdateExistsError,
    ProfessorUpdateService,
)


class DiscoveryProvider(Protocol):
    async def discover(self) -> list[FacultyCandidate]: ...


class CandidateResearchProvider(Protocol):
    async def research(self, candidate: FacultyCandidate) -> ValidatedProfessorResearch: ...


class JobLevelUpdateError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _source_hash(candidate: FacultyCandidate, research: ValidatedProfessorResearch) -> str:
    payload = {
        "identity": {
            "name": candidate.name,
            "title": candidate.title,
            "email": candidate.email,
            "directory_profile_url": candidate.directory_profile_url,
        },
        "research": research.model_dump(mode="json"),
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LangGraphCandidateResearcher:
    def __init__(
        self,
        *,
        chat_model: Any,
        tavily: TavilyProvider,
        openalex: OpenAlexProvider,
        page_http: RateLimitedHttpClient,
    ) -> None:
        self.chat_model = chat_model
        self.tavily = tavily
        self.openalex = openalex
        self.page_http = page_http

    async def research(self, candidate: FacultyCandidate) -> ValidatedProfessorResearch:
        return await self._research(candidate, required_refresh=False)

    async def research_with_refresh(
        self,
        candidate: FacultyCandidate,
    ) -> ValidatedProfessorResearch:
        return await self._research(candidate, required_refresh=True)

    async def _research(
        self,
        candidate: FacultyCandidate,
        *,
        required_refresh: bool,
    ) -> ValidatedProfessorResearch:
        identity = ResearchIdentity(
            name=candidate.name,
            email=candidate.email,
            title=candidate.title,
            affiliation=candidate.affiliation,
            official_profile_url=candidate.directory_profile_url,
        )
        registry = CandidateSourceRegistry()
        registry.register_hit(
            SearchHit(
                title=f"Official UIUC profile for {candidate.name}",
                url=candidate.directory_profile_url,
                snippet="Official UIUC ECE faculty profile.",
            )
        )
        preloaded_sources = []
        initial_publications = []
        if required_refresh:
            refresh_hits = await self.tavily.search(
                f"{candidate.name} UIUC ECE research lab publications"
            )
            preloaded_sources = registry.register_hits(refresh_hits)
            initial_publications = await self.openalex.get_recent_publications(identity)
        page_extractor = PageExtractor(self.page_http, registry)
        tools = create_research_tools(
            identity=identity,
            registry=registry,
            tavily=self.tavily,
            page_extractor=page_extractor,
            openalex=self.openalex,
        )
        return await ProfessorResearchGraph(
            identity=identity,
            chat_model=self.chat_model,
            tools=tools,
            registry=registry,
            initial_publications=initial_publications,
            preloaded_sources=preloaded_sources,
        ).ainvoke()


class UpdateCheckService:
    def __init__(
        self,
        *,
        database_path: Path,
        jobs: JobRegistry,
        discovery: DiscoveryProvider,
        researcher: CandidateResearchProvider,
        professor_updates: ProfessorUpdateService | None = None,
    ) -> None:
        self.database_path = database_path
        self.jobs = jobs
        self.discovery = discovery
        self.researcher = researcher
        self.professor_updates = professor_updates
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start_new(self) -> JobSnapshot:
        job = await self.jobs.create(JobScope.NEW)
        task = asyncio.create_task(
            self._run_new(job.job_id),
            name=f"update-check-{job.job_id}",
        )
        self._tasks[job.job_id] = task
        return job

    async def get_job(self, job_id: str) -> JobSnapshot:
        return await self.jobs.get(job_id)

    async def start_professor(self, professor_id: int) -> JobSnapshot:
        if self.professor_updates is None:
            raise RuntimeError("Single-professor updates are not configured")
        self.professor_updates.validate_check_start(professor_id)
        job = await self.jobs.create(JobScope.PROFESSOR, professor_id=professor_id)
        task = asyncio.create_task(
            self._run_professor(job.job_id, professor_id),
            name=f"update-check-{job.job_id}",
        )
        self._tasks[job.job_id] = task
        return job

    async def wait(self, job_id: str) -> None:
        task = self._tasks.get(job_id)
        if task is not None:
            await task

    async def shutdown(self) -> None:
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_new(self, job_id: str) -> None:
        await self.jobs.mark_running(job_id)
        try:
            discovered = await self.discovery.discover()
        except Exception as error:  # noqa: BLE001 - converted to job-level state
            code, message = self._job_level_error(error, default_code="DIRECTORY_DISCOVERY_FAILED")
            await self.jobs.fail(job_id, error_code=code, error_message=message)
            return

        with connect_database(self.database_path) as connection:
            run_migrations(connection)
            existing_records = ProfessorsRepository(connection).list_all()
        identities = IdentityIndex(
            ExistingProfessorIdentity(
                professor_id=record.id,
                name=record.name,
                email=record.email,
                directory_profile_url=record.directory_profile_url,
            )
            for record in existing_records
        )

        work_items: list[tuple[FacultyCandidate, AmbiguousIdentityError | None]] = []
        for candidate in discovered:
            try:
                existing_id = identities.match(candidate)
            except AmbiguousIdentityError as error:
                work_items.append((candidate, error))
                continue
            if existing_id is None:
                work_items.append((candidate, None))

        discovered_count = len(work_items)
        processed_count = 0
        added_count = 0
        failed_count = 0
        await self.jobs.update_new_counts(
            job_id,
            discovered_count=discovered_count,
            processed_count=0,
            added_count=0,
            failed_count=0,
        )

        for candidate, identity_error in work_items:
            try:
                if identity_error is not None:
                    raise identity_error
                research = await self.researcher.research(candidate)
                self._persist_professor(candidate, research)
            except Exception as error:  # noqa: BLE001 - candidate isolation is intentional
                processed_count += 1
                failed_count += 1
                await self.jobs.update_new_counts(
                    job_id,
                    discovered_count=discovered_count,
                    processed_count=processed_count,
                    added_count=added_count,
                    failed_count=failed_count,
                )
                job_level = self._job_level_error_or_none(error)
                if job_level is not None:
                    await self.jobs.fail(
                        job_id,
                        error_code=job_level[0],
                        error_message=job_level[1],
                    )
                    return
                continue

            processed_count += 1
            added_count += 1
            await self.jobs.update_new_counts(
                job_id,
                discovered_count=discovered_count,
                processed_count=processed_count,
                added_count=added_count,
                failed_count=failed_count,
            )

        await self.jobs.complete_new(job_id)

    async def _run_professor(self, job_id: str, professor_id: int) -> None:
        await self.jobs.mark_running(job_id)
        if self.professor_updates is None:
            await self.jobs.fail(
                job_id,
                error_code="SINGLE_CHECK_NOT_CONFIGURED",
                error_message="Single-professor updates are not configured.",
            )
            return
        try:
            changed, proposal_id = await self.professor_updates.check(professor_id, job_id)
        except PendingUpdateExistsError as error:
            await self.jobs.complete_professor(
                job_id,
                changed=True,
                proposal_id=error.proposal_id,
            )
        except Exception as error:  # noqa: BLE001 - converted to terminal job state
            code, message = self._job_level_error(
                error,
                default_code="PROFESSOR_CHECK_FAILED",
            )
            await self.jobs.fail(job_id, error_code=code, error_message=message)
        else:
            await self.jobs.complete_professor(
                job_id,
                changed=changed,
                proposal_id=proposal_id,
            )

    def _persist_professor(
        self,
        candidate: FacultyCandidate,
        research: ValidatedProfessorResearch,
    ) -> None:
        now = datetime.now(UTC)
        source_urls = list(
            dict.fromkeys([candidate.directory_profile_url, *research.source_urls])
        )
        professor = ProfessorCreate(
            name=candidate.name,
            title=candidate.title,
            email=candidate.email,
            directory_profile_url=candidate.directory_profile_url,
            homepage_url=research.homepage_url,
            lab_url=research.lab_url,
            research_summary=research.research_summary,
            tags=research.tags,
            source_urls=source_urls,
            source_hash=_source_hash(candidate, research),
        )
        publications = [
            PublicationCreate(
                title=publication.title,
                year=publication.year,
                venue=publication.venue,
                publication_url=publication.publication_url,
                doi=publication.doi,
                source="openalex",
            )
            for publication in research.publications
        ]
        with connect_database(self.database_path) as connection, transaction(connection):
            created = ProfessorsRepository(connection).create(professor, now=now)
            PublicationsRepository(connection).create_many(
                created.id,
                publications,
                now=now,
            )

    @staticmethod
    def _job_level_error_or_none(error: Exception) -> tuple[str, str] | None:
        if isinstance(error, JobLevelUpdateError):
            return error.code, error.message
        is_provider_access_error = (
            isinstance(error, httpx.HTTPStatusError)
            and error.response.status_code in {401, 403, 429}
        )
        if is_provider_access_error:
            return "PROVIDER_ACCESS_FAILED", str(error)
        return None

    @classmethod
    def _job_level_error(cls, error: Exception, *, default_code: str) -> tuple[str, str]:
        return cls._job_level_error_or_none(error) or (default_code, str(error))


def build_default_update_check_service(
    *,
    settings: Settings,
    jobs: JobRegistry,
    http_client: httpx.AsyncClient,
) -> UpdateCheckService:
    page_http = RateLimitedHttpClient(
        http_client,
        SerialRateLimiter(settings.web_host_min_interval_seconds),
    )
    openalex_http = RateLimitedHttpClient(
        http_client,
        SerialRateLimiter(settings.openalex_min_interval_seconds),
    )
    tavily = TavilyProvider(
        limiter=SerialRateLimiter(settings.tavily_min_interval_seconds),
        api_key=settings.tavily_api_key,
    )
    openalex = OpenAlexProvider(openalex_http, api_key=settings.openalex_api_key)
    chat_kwargs: dict[str, object] = {
        "model": settings.llm_model,
        "api_key": settings.llm_api_key.get_secret_value(),
    }
    if settings.llm_base_url is not None:
        chat_kwargs["base_url"] = str(settings.llm_base_url)
    chat_model = ChatOpenAI(**chat_kwargs)
    researcher = LangGraphCandidateResearcher(
        chat_model=chat_model,
        tavily=tavily,
        openalex=openalex,
        page_http=page_http,
    )
    professor_updates = ProfessorUpdateService(settings.database_path, researcher)
    return UpdateCheckService(
        database_path=settings.database_path,
        jobs=jobs,
        discovery=FacultyDiscoveryClient(page_http),
        researcher=researcher,
        professor_updates=professor_updates,
    )
