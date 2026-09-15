from pathlib import Path

from fastapi.testclient import TestClient

from lab_tracker.config import Settings
from lab_tracker.main import create_app


class IdleUpdateService:
    professor_updates = None

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


def test_serves_built_frontend_with_spa_fallback_and_keeps_api_priority(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<main>Lab Tracker SPA</main>", encoding="utf-8")
    (assets / "app.js").write_text("window.appLoaded = true;", encoding="utf-8")
    app = create_app(
        settings=settings(tmp_path / "static.db"),
        update_check_service=IdleUpdateService(),
        frontend_dist_path=dist,
    )

    with TestClient(app) as client:
        root = client.get("/")
        client_route = client.get("/professors/123")
        asset = client.get("/assets/app.js")
        health = client.get("/api/health")
        missing_api = client.get("/api/does-not-exist")

    assert root.status_code == 200
    assert client_route.text == root.text
    assert root.headers["cache-control"] == "no-cache"
    assert client_route.headers["cache-control"] == "no-cache"
    assert asset.text == "window.appLoaded = true;"
    assert health.json() == {"status": "ok", "database": "ok"}
    assert missing_api.status_code == 404
    assert "Lab Tracker SPA" not in missing_api.text
