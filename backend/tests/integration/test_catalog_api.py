from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from lab_tracker.config import Settings
from lab_tracker.db.connection import connect_database
from lab_tracker.db.migrations import run_migrations
from lab_tracker.main import create_app
from lab_tracker.models.professor import ProfessorCreate
from lab_tracker.models.publication import PublicationCreate
from lab_tracker.repositories.professors import ProfessorsRepository
from lab_tracker.repositories.publications import PublicationsRepository

NOW = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


def make_test_settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=database_path,
        llm_api_key="test-llm-key",
        llm_model="test-model",
        tavily_api_key="test-tavily-key",
        openalex_api_key="test-openalex-key",
    )


def seed_catalog(database_path: Path) -> int:
    with connect_database(database_path) as connection:
        run_migrations(connection)
        professors = ProfessorsRepository(connection)
        publications = PublicationsRepository(connection)
        alice = professors.create(
            ProfessorCreate(
                name="Alice Systems",
                title="Professor",
                email="alice@illinois.edu",
                official_profile_url="https://ece.illinois.edu/alice",
                personal_homepage_url="https://alice.example.edu/lab",
                research_summary="Reliable computer architecture.",
                tags=["Architecture", "Reliable AI"],
                source_urls=["https://ece.illinois.edu/alice"],
                source_hash="alice-hash",
            ),
            now=NOW,
        )
        professors.create(
            ProfessorCreate(
                name="Bob Circuits",
                title="Associate Professor",
                official_profile_url="https://ece.illinois.edu/bob",
                research_summary="Integrated circuit design.",
                tags=["Circuits"],
                source_hash="bob-hash",
            ),
            now=NOW,
        )
        publications.create_many(
            alice.id,
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
        return alice.id


def test_health_catalog_detail_and_tags_endpoints(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog-api.db"
    alice_id = seed_catalog(database_path)
    app = create_app(settings=make_test_settings(database_path))

    with TestClient(app) as client:
        health = client.get("/api/health")
        catalog = client.get("/api/professors", params={"page": 1, "page_size": 1})
        filtered = client.get(
            "/api/professors",
            params={"q": "architecture", "tags": "reliable ai"},
        )
        detail = client.get(f"/api/professors/{alice_id}")
        tags = client.get("/api/tags")

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "database": "ok"}

    assert catalog.status_code == 200
    assert len(catalog.json()["items"]) == 1
    assert catalog.json()["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total": 2,
        "pages": 2,
    }
    assert filtered.status_code == 200
    assert [item["name"] for item in filtered.json()["items"]] == ["Alice Systems"]
    assert filtered.json()["items"][0]["application_state"] is None

    assert detail.status_code == 200
    assert detail.json()["name"] == "Alice Systems"
    assert detail.json()["publications"][0]["title"] == "Reliable Accelerators"
    assert detail.json()["application"] is None
    assert detail.json()["pending_proposal_id"] is None

    assert tags.status_code == 200
    assert {(item["tag"], item["professor_count"]) for item in tags.json()["items"]} == {
        ("architecture", 1),
        ("circuits", 1),
        ("reliable ai", 1),
    }


def test_catalog_api_uses_error_envelope_for_not_found_and_validation(tmp_path: Path) -> None:
    database_path = tmp_path / "catalog-errors.db"
    seed_catalog(database_path)
    app = create_app(settings=make_test_settings(database_path))

    with TestClient(app) as client:
        missing = client.get("/api/professors/99999")
        invalid_state = client.get("/api/professors", params={"state": "not_tracked"})
        invalid_sort = client.get("/api/professors", params={"sort": "name; DROP TABLE professors"})

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PROFESSOR_NOT_FOUND"
    assert invalid_state.status_code == 422
    assert invalid_state.json()["error"]["code"] == "VALIDATION_ERROR"
    assert invalid_sort.status_code == 422
    assert invalid_sort.json()["error"]["code"] == "VALIDATION_ERROR"
