from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from lab_tracker.config import Settings
from lab_tracker.db.connection import connect_database
from lab_tracker.db.migrations import run_migrations
from lab_tracker.main import create_app
from lab_tracker.models.professor import ProfessorCreate
from lab_tracker.repositories.professors import ProfessorsRepository

NOW = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


def build_test_app(database_path: Path) -> tuple[TestClient, int]:
    with connect_database(database_path) as connection:
        run_migrations(connection)
        professor = ProfessorsRepository(connection).create(
            ProfessorCreate(
                name="Alice Systems",
                title="Professor",
                email="alice@illinois.edu",
                official_profile_url="https://ece.illinois.edu/alice",
                research_summary="Original research summary.",
                tags=["Architecture"],
                source_hash="alice-hash",
            ),
            now=NOW,
        )

    settings = Settings(
        _env_file=None,
        database_path=database_path,
        llm_api_key="test-llm-key",
        llm_model="test-model",
        tavily_api_key="test-tavily-key",
        openalex_api_key="test-openalex-key",
    )
    return TestClient(create_app(settings=settings)), professor.id


def test_application_put_is_an_idempotent_upsert_and_delete_clears_tracking(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "application-api.db"
    client, professor_id = build_test_app(database_path)

    with client:
        created = client.put(
            f"/api/professors/{professor_id}/application",
            json={"state": "interested", "application_date": None, "notes": "Drafting."},
        )
        updated = client.put(
            f"/api/professors/{professor_id}/application",
            json={
                "state": "applied",
                "application_date": "2026-08-16",
                "notes": "Submitted.",
            },
        )
        detail_before_delete = client.get(f"/api/professors/{professor_id}")
        deleted = client.delete(f"/api/professors/{professor_id}/application")
        detail_after_delete = client.get(f"/api/professors/{professor_id}")

    assert created.status_code == 200
    assert created.json()["state"] == "interested"
    assert updated.status_code == 200
    assert updated.json()["state"] == "applied"
    assert updated.json()["application_date"] == "2026-08-16"
    assert detail_before_delete.json()["application"]["notes"] == "Submitted."
    assert deleted.status_code == 204
    assert detail_after_delete.json()["application"] is None
    assert detail_after_delete.json()["research_summary"] == "Original research summary."

    with connect_database(database_path) as connection:
        professor_row = connection.execute(
            "SELECT research_summary FROM professors WHERE id = ?", (professor_id,)
        ).fetchone()
        application_count = connection.execute(
            "SELECT COUNT(*) FROM application_status WHERE professor_id = ?", (professor_id,)
        ).fetchone()[0]
    assert professor_row["research_summary"] == "Original research summary."
    assert application_count == 0


def test_application_api_rejects_missing_professor_and_invalid_state(tmp_path: Path) -> None:
    client, professor_id = build_test_app(tmp_path / "application-errors.db")

    with client:
        missing = client.put(
            "/api/professors/99999/application",
            json={"state": "interested"},
        )
        invalid = client.put(
            f"/api/professors/{professor_id}/application",
            json={"state": "not_tracked"},
        )
        missing_delete = client.delete("/api/professors/99999/application")

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PROFESSOR_NOT_FOUND"
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    assert missing_delete.status_code == 404
    assert missing_delete.json()["error"]["code"] == "PROFESSOR_NOT_FOUND"
