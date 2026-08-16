"""Request-scoped FastAPI dependencies."""

from pathlib import Path

from fastapi import Request


def get_database_path(request: Request) -> Path:
    """Return the configured path without sharing a SQLite connection across threads."""

    return request.app.state.settings.database_path
