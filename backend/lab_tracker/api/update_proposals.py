"""Inspect, apply, and reject single-professor update proposals."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from lab_tracker.api.professors import PaginationMetadata
from lab_tracker.errors import AppError
from lab_tracker.models.common import ProposalStatus
from lab_tracker.models.update import ProposalRecord
from lab_tracker.services.updates import (
    ProfessorUpdateService,
    ProposalApplyError,
    ProposalNotFoundError,
    ProposalNotPendingError,
)

router = APIRouter(prefix="/api/update-proposals", tags=["updates"])


def get_professor_update_service(request: Request) -> ProfessorUpdateService:
    return request.app.state.professor_update_service


class ProposalListResponse(BaseModel):
    items: list[ProposalRecord]
    pagination: PaginationMetadata


@router.get("", response_model=ProposalListResponse)
def list_proposals(
    service: Annotated[ProfessorUpdateService, Depends(get_professor_update_service)],
    status: ProposalStatus | None = None,
    professor_id: int | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ProposalListResponse:
    items, total = service.list_proposals(
        status=status,
        professor_id=professor_id,
        page=page,
        page_size=page_size,
    )
    return ProposalListResponse(
        items=items,
        pagination=PaginationMetadata(
            page=page,
            page_size=page_size,
            total=total,
            pages=(total + page_size - 1) // page_size,
        ),
    )


@router.get("/{proposal_id}", response_model=ProposalRecord)
def get_proposal(
    proposal_id: int,
    service: Annotated[ProfessorUpdateService, Depends(get_professor_update_service)],
) -> ProposalRecord:
    try:
        return service.get_proposal(proposal_id)
    except ProposalNotFoundError as error:
        raise _proposal_not_found(proposal_id) from error


@router.post("/{proposal_id}/apply", response_model=ProposalRecord)
def apply_proposal(
    proposal_id: int,
    service: Annotated[ProfessorUpdateService, Depends(get_professor_update_service)],
) -> ProposalRecord:
    try:
        return service.apply(proposal_id)
    except ProposalNotFoundError as error:
        raise _proposal_not_found(proposal_id) from error
    except ProposalNotPendingError as error:
        raise _proposal_not_pending(proposal_id) from error
    except ProposalApplyError as error:
        raise AppError(
            code="PROPOSAL_APPLY_FAILED",
            message="The proposal could not be applied; it remains pending.",
            status_code=500,
            details={"proposal_id": proposal_id},
        ) from error


@router.post("/{proposal_id}/reject", response_model=ProposalRecord)
def reject_proposal(
    proposal_id: int,
    service: Annotated[ProfessorUpdateService, Depends(get_professor_update_service)],
) -> ProposalRecord:
    try:
        return service.reject(proposal_id)
    except ProposalNotFoundError as error:
        raise _proposal_not_found(proposal_id) from error
    except ProposalNotPendingError as error:
        raise _proposal_not_pending(proposal_id) from error


def _proposal_not_found(proposal_id: int) -> AppError:
    return AppError(
        code="PROPOSAL_NOT_FOUND",
        message=f"Proposal {proposal_id} was not found.",
        status_code=404,
        details={"proposal_id": proposal_id},
    )


def _proposal_not_pending(proposal_id: int) -> AppError:
    return AppError(
        code="PROPOSAL_NOT_PENDING",
        message=f"Proposal {proposal_id} is no longer pending.",
        status_code=409,
        details={"proposal_id": proposal_id},
    )
