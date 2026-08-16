from pathlib import Path

from fastapi.testclient import TestClient

from lab_tracker.config import Settings
from lab_tracker.main import create_app
from lab_tracker.services.jobs import JobRegistry, JobScope, JobSnapshot


class QueuedUpdateService:
    def __init__(self) -> None:
        self.jobs = JobRegistry()

    async def start_new(self) -> JobSnapshot:
        return await self.jobs.create(JobScope.NEW)

    async def get_job(self, job_id: str) -> JobSnapshot:
        return await self.jobs.get(job_id)

    async def shutdown(self) -> None:
        return None


def settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=database_path,
        llm_api_key="test-llm-key",
        llm_model="test-model",
        tavily_api_key="test-tavily-key",
        openalex_api_key="test-openalex-key",
    )


def test_update_check_api_returns_202_conflict_with_active_id_and_404_for_unknown(
    tmp_path: Path,
) -> None:
    service = QueuedUpdateService()
    app = create_app(
        settings=settings(tmp_path / "update-check-api.db"),
        update_check_service=service,
    )

    with TestClient(app) as client:
        started = client.post("/api/update-checks", json={"scope": "new"})
        active_job_id = started.json()["job_id"]
        conflict = client.post("/api/update-checks", json={"scope": "new"})
        polled = client.get(f"/api/update-checks/{active_job_id}")
        missing = client.get("/api/update-checks/old-process-job-id")

    assert started.status_code == 202
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "UPDATE_ALREADY_RUNNING"
    assert conflict.json()["error"]["details"]["job_id"] == active_job_id
    assert polled.status_code == 200
    assert polled.json()["status"] == "queued"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "UPDATE_JOB_NOT_FOUND"
