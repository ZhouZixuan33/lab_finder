"""Application tracking endpoints."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from lab_tracker.api.dependencies import get_database_path
from lab_tracker.models.application import ApplicationRecord, ApplicationUpsert
from lab_tracker.services.applications import ApplicationService

router = APIRouter(prefix="/api/professors", tags=["applications"])


@router.put("/{professor_id}/application", response_model=ApplicationRecord)
def upsert_application(
    professor_id: int,
    application: ApplicationUpsert,
    database_path: Annotated[Path, Depends(get_database_path)],
) -> ApplicationRecord:
    return ApplicationService(database_path).upsert(professor_id, application)


@router.delete("/{professor_id}/application", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(
    professor_id: int,
    database_path: Annotated[Path, Depends(get_database_path)],
) -> Response:
    ApplicationService(database_path).delete(professor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
