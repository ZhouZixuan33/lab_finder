"""FastAPI application factory and production entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from lab_tracker.api.applications import router as applications_router
from lab_tracker.api.health import router as health_router
from lab_tracker.api.professors import router as professors_router
from lab_tracker.api.update_checks import router as update_checks_router
from lab_tracker.api.update_proposals import router as update_proposals_router
from lab_tracker.config import Settings, get_settings
from lab_tracker.db.connection import connect_database
from lab_tracker.db.migrations import run_migrations
from lab_tracker.errors import register_error_handlers
from lab_tracker.services.jobs import JobRegistry
from lab_tracker.services.update_checks import build_default_update_check_service


class SpaStaticFiles(StaticFiles):
    """Serve built assets and fall back to index.html for client-side routes."""

    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404 and not path.startswith("api/"):
            return await super().get_response("index.html", scope)
        return response


def create_app(
    *,
    settings: Settings | None = None,
    update_check_service: Any | None = None,
    frontend_dist_path: Path | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime_settings = settings or get_settings()
        application.state.settings = runtime_settings
        with connect_database(runtime_settings.database_path) as connection:
            run_migrations(connection)

        external_http: httpx.AsyncClient | None = None
        service = update_check_service
        if service is None:
            external_http = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                headers={"User-Agent": "LabApplicationTracker/0.1"},
            )
            service = build_default_update_check_service(
                settings=runtime_settings,
                jobs=JobRegistry(),
                http_client=external_http,
            )
        application.state.update_check_service = service
        application.state.professor_update_service = getattr(
            service,
            "professor_updates",
            None,
        )
        try:
            yield
        finally:
            await service.shutdown()
            if external_http is not None:
                await external_http.aclose()

    application = FastAPI(
        title="Lab Application Tracker",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_error_handlers(application)
    application.include_router(health_router)
    application.include_router(professors_router)
    application.include_router(applications_router)
    application.include_router(update_checks_router)
    application.include_router(update_proposals_router)

    @application.api_route(
        "/api/{unmatched_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    async def unmatched_api(unmatched_path: str) -> None:
        raise HTTPException(status_code=404, detail=f"Unknown API path: /api/{unmatched_path}")

    dist_path = frontend_dist_path or Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if (dist_path / "index.html").is_file():
        application.mount("/", SpaStaticFiles(directory=dist_path, html=True), name="frontend")
    return application


app = create_app()
