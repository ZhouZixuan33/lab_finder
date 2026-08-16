"""FastAPI application factory and production entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from lab_tracker.api.applications import router as applications_router
from lab_tracker.api.health import router as health_router
from lab_tracker.api.professors import router as professors_router
from lab_tracker.config import Settings, get_settings
from lab_tracker.db.connection import connect_database
from lab_tracker.db.migrations import run_migrations
from lab_tracker.errors import register_error_handlers


def create_app(*, settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime_settings = settings or get_settings()
        application.state.settings = runtime_settings
        with connect_database(runtime_settings.database_path) as connection:
            run_migrations(connection)
        yield

    application = FastAPI(
        title="Lab Application Tracker",
        version="0.1.0",
        lifespan=lifespan,
    )
    register_error_handlers(application)
    application.include_router(health_router)
    application.include_router(professors_router)
    application.include_router(applications_router)
    return application


app = create_app()
