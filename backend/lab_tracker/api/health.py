"""Process and database health endpoint."""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from lab_tracker.api.dependencies import get_database_path
from lab_tracker.db.connection import connect_database

router = APIRouter(prefix="/api", tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]


@router.get("/health", response_model=HealthResponse)
def health_check(
    database_path: Annotated[Path, Depends(get_database_path)],
) -> HealthResponse:
    with connect_database(database_path) as connection:
        connection.execute("SELECT 1").fetchone()
    return HealthResponse(status="ok", database="ok")
