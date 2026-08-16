"""Single-process in-memory update job registry."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from lab_tracker.models.common import DomainModel


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobScope(StrEnum):
    NEW = "new"
    PROFESSOR = "professor"


class JobOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    NO_CHANGES = "no_changes"
    ALL_FAILED = "all_failed"


class JobSnapshot(DomainModel):
    job_id: str
    scope: JobScope
    status: JobStatus
    professor_id: int | None = None
    outcome: JobOutcome | None = None
    discovered_count: int = 0
    processed_count: int = 0
    added_count: int = 0
    failed_count: int = 0
    changed: bool | None = None
    proposal_id: int | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class _MutableJob:
    job_id: str
    scope: JobScope
    status: JobStatus = JobStatus.QUEUED
    professor_id: int | None = None
    outcome: JobOutcome | None = None
    discovered_count: int = 0
    processed_count: int = 0
    added_count: int = 0
    failed_count: int = 0
    changed: bool | None = None
    proposal_id: int | None = None
    error_code: str | None = None
    error_message: str | None = None

    def snapshot(self) -> JobSnapshot:
        return JobSnapshot.model_validate(self.__dict__)


class ActiveJobError(RuntimeError):
    def __init__(self, active_job_id: str) -> None:
        super().__init__(f"Update job {active_job_id} is already active")
        self.active_job_id = active_job_id


class JobNotFoundError(LookupError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Update job {job_id} was not found")
        self.job_id = job_id


def calculate_new_job_outcome(
    discovered_count: int,
    added_count: int,
    failed_count: int,
) -> JobOutcome:
    if discovered_count == 0:
        return JobOutcome.NO_CHANGES
    if added_count == discovered_count and failed_count == 0:
        return JobOutcome.SUCCESS
    if added_count > 0 and failed_count > 0:
        return JobOutcome.PARTIAL_SUCCESS
    if added_count == 0 and failed_count == discovered_count:
        return JobOutcome.ALL_FAILED
    raise ValueError("New-professor counts do not describe a valid completed outcome")


class JobRegistry:
    def __init__(self, *, id_factory: Callable[[], object] = uuid4) -> None:
        self._id_factory = id_factory
        self._jobs: dict[str, _MutableJob] = {}
        self._active_job_id: str | None = None
        self._lock = asyncio.Lock()

    async def create(
        self,
        scope: JobScope,
        *,
        professor_id: int | None = None,
    ) -> JobSnapshot:
        async with self._lock:
            if self._active_job_id is not None:
                active = self._jobs[self._active_job_id]
                if active.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                    raise ActiveJobError(active.job_id)
                self._active_job_id = None

            job_id = str(self._id_factory())
            job = _MutableJob(job_id=job_id, scope=scope, professor_id=professor_id)
            self._jobs[job_id] = job
            self._active_job_id = job_id
            return job.snapshot()

    async def get(self, job_id: str) -> JobSnapshot:
        async with self._lock:
            return self._get_mutable(job_id).snapshot()

    async def mark_running(self, job_id: str) -> JobSnapshot:
        async with self._lock:
            job = self._get_mutable(job_id)
            job.status = JobStatus.RUNNING
            return job.snapshot()

    async def update_new_counts(
        self,
        job_id: str,
        *,
        discovered_count: int,
        processed_count: int,
        added_count: int,
        failed_count: int,
    ) -> JobSnapshot:
        async with self._lock:
            job = self._get_mutable(job_id)
            job.discovered_count = discovered_count
            job.processed_count = processed_count
            job.added_count = added_count
            job.failed_count = failed_count
            return job.snapshot()

    async def complete_new(self, job_id: str) -> JobSnapshot:
        async with self._lock:
            job = self._get_mutable(job_id)
            if job.processed_count != job.discovered_count:
                raise ValueError(
                    "Completed new-professor job must process every discovered candidate"
                )
            if job.added_count + job.failed_count != job.processed_count:
                raise ValueError(
                    "Completed new-professor job counts violate the processing invariant"
                )
            job.outcome = calculate_new_job_outcome(
                job.discovered_count,
                job.added_count,
                job.failed_count,
            )
            job.status = JobStatus.COMPLETED
            self._clear_active(job_id)
            return job.snapshot()

    async def complete_professor(
        self,
        job_id: str,
        *,
        changed: bool,
        proposal_id: int | None,
    ) -> JobSnapshot:
        async with self._lock:
            job = self._get_mutable(job_id)
            job.changed = changed
            job.proposal_id = proposal_id
            job.status = JobStatus.COMPLETED
            self._clear_active(job_id)
            return job.snapshot()

    async def fail(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> JobSnapshot:
        async with self._lock:
            job = self._get_mutable(job_id)
            job.status = JobStatus.FAILED
            job.error_code = error_code
            job.error_message = error_message
            self._clear_active(job_id)
            return job.snapshot()

    def _get_mutable(self, job_id: str) -> _MutableJob:
        try:
            return self._jobs[job_id]
        except KeyError as error:
            raise JobNotFoundError(job_id) from error

    def _clear_active(self, job_id: str) -> None:
        if self._active_job_id == job_id:
            self._active_job_id = None
