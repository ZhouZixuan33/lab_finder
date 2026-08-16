"""FastAPI application factory and production entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

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


def create_app(
    *,
    settings: Settings | None = None,
    update_check_service: Any | None = None,
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
    return application


app = create_app()
