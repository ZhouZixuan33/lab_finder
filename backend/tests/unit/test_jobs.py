from uuid import UUID

import pytest

from lab_tracker.services.jobs import (
    ActiveJobError,
    JobNotFoundError,
    JobOutcome,
    JobRegistry,
    JobScope,
    JobStatus,
    calculate_new_job_outcome,
)


@pytest.mark.asyncio
async def test_registry_uses_uuid_strings_and_allows_only_one_active_job() -> None:
    registry = JobRegistry()
    created = await registry.create(JobScope.NEW)

    assert str(UUID(created.job_id)) == created.job_id
    assert created.status is JobStatus.QUEUED

    with pytest.raises(ActiveJobError) as error:
        await registry.create(JobScope.NEW)
    assert error.value.active_job_id == created.job_id

    await registry.mark_running(created.job_id)
    await registry.update_new_counts(
        created.job_id,
        discovered_count=3,
        processed_count=3,
        added_count=2,
        failed_count=1,
    )
    completed = await registry.complete_new(created.job_id)

    assert completed.status is JobStatus.COMPLETED
    assert completed.outcome is JobOutcome.PARTIAL_SUCCESS
    assert completed.added_count == 2
    assert (await registry.create(JobScope.NEW)).status is JobStatus.QUEUED


@pytest.mark.asyncio
async def test_unknown_job_is_not_reconstructed_after_registry_restart() -> None:
    registry = JobRegistry()

    with pytest.raises(JobNotFoundError):
        await registry.get("old-process-job-id")


@pytest.mark.parametrize(
    ("discovered", "added", "failed", "expected"),
    [
        (0, 0, 0, JobOutcome.NO_CHANGES),
        (3, 3, 0, JobOutcome.SUCCESS),
        (3, 2, 1, JobOutcome.PARTIAL_SUCCESS),
        (3, 0, 3, JobOutcome.ALL_FAILED),
    ],
)
def test_new_job_outcome_is_deterministic(
    discovered: int,
    added: int,
    failed: int,
    expected: JobOutcome,
) -> None:
    assert calculate_new_job_outcome(discovered, added, failed) is expected
