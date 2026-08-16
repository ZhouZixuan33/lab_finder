"""Start and poll in-memory update checks."""

from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, model_validator

from lab_tracker.errors import AppError
from lab_tracker.services.jobs import (
    ActiveJobError,
    JobNotFoundError,
    JobScope,
    JobSnapshot,
)

router = APIRouter(prefix="/api/update-checks", tags=["updates"])


class UpdateCheckServiceProtocol(Protocol):
    async def start_new(self) -> JobSnapshot: ...

    async def get_job(self, job_id: str) -> JobSnapshot: ...


def get_update_check_service(request: Request) -> UpdateCheckServiceProtocol:
    return request.app.state.update_check_service


class StartUpdateCheckRequest(BaseModel):
    scope: JobScope
    professor_id: int | None = None

    @model_validator(mode="after")
    def validate_scope_fields(self) -> "StartUpdateCheckRequest":
        if self.scope is JobScope.NEW and self.professor_id is not None:
            raise ValueError("professor_id is not allowed for scope=new")
        if self.scope is JobScope.PROFESSOR and self.professor_id is None:
            raise ValueError("professor_id is required for scope=professor")
        return self


class StartUpdateCheckResponse(BaseModel):
    job_id: str


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=StartUpdateCheckResponse)
async def start_update_check(
    request: StartUpdateCheckRequest,
    service: Annotated[UpdateCheckServiceProtocol, Depends(get_update_check_service)],
) -> StartUpdateCheckResponse:
    if request.scope is not JobScope.NEW:
        raise AppError(
            code="UNSUPPORTED_UPDATE_SCOPE",
            message="Single-professor checks are not available yet.",
            status_code=400,
        )
    try:
        job = await service.start_new()
    except ActiveJobError as error:
        raise AppError(
            code="UPDATE_ALREADY_RUNNING",
            message="Another update check is already running.",
            status_code=409,
            details={"job_id": error.active_job_id},
        ) from error
    return StartUpdateCheckResponse(job_id=job.job_id)


@router.get("/{job_id}", response_model=JobSnapshot)
async def get_update_check(
    job_id: str,
    service: Annotated[UpdateCheckServiceProtocol, Depends(get_update_check_service)],
) -> JobSnapshot:
    try:
        return await service.get_job(job_id)
    except JobNotFoundError as error:
        raise AppError(
            code="UPDATE_JOB_NOT_FOUND",
            message="The update job is unknown or belonged to a previous server process.",
            status_code=404,
            details={"job_id": job_id},
        ) from error
