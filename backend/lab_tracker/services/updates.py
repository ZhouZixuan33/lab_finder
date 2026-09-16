"""Single-professor checks and transactional proposal resolution."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from lab_tracker.db.connection import connect_database, transaction
from lab_tracker.diagnostics import (
    emit_professor_extracted,
    emit_professor_research_failed,
)
from lab_tracker.errors import ProfessorNotFoundError
from lab_tracker.models.common import ProposalStatus
from lab_tracker.models.professor import ProfessorCreate
from lab_tracker.models.publication import PublicationCreate
from lab_tracker.models.research import ValidatedProfessorResearch
from lab_tracker.models.update import ProposalCreate, ProposalRecord
from lab_tracker.repositories.professors import ProfessorsRepository
from lab_tracker.repositories.proposals import ProposalsRepository
from lab_tracker.repositories.publications import PublicationsRepository
from lab_tracker.services.diff import (
    ProfessorUpdateSnapshot,
    PublicationDifference,
    compare_professor_update,
)
from lab_tracker.services.discovery import FacultyCandidate


class RefreshResearchProvider(Protocol):
    async def research_with_refresh(
        self,
        candidate: FacultyCandidate,
    ) -> ValidatedProfessorResearch: ...


class PendingUpdateExistsError(RuntimeError):
    def __init__(self, proposal_id: int) -> None:
        super().__init__(f"Pending proposal {proposal_id} already exists")
        self.proposal_id = proposal_id


class ProposalNotFoundError(LookupError):
    def __init__(self, proposal_id: int) -> None:
        super().__init__(f"Proposal {proposal_id} was not found")
        self.proposal_id = proposal_id


class ProposalNotPendingError(RuntimeError):
    def __init__(self, proposal_id: int) -> None:
        super().__init__(f"Proposal {proposal_id} is no longer pending")
        self.proposal_id = proposal_id


class ProposalApplyError(RuntimeError):
    pass


class ProfessorUpdateService:
    def __init__(self, database_path: Path, researcher: RefreshResearchProvider) -> None:
        self.database_path = database_path
        self.researcher = researcher

    def validate_check_start(self, professor_id: int) -> None:
        with connect_database(self.database_path) as connection:
            if ProfessorsRepository(connection).get(professor_id) is None:
                raise ProfessorNotFoundError(professor_id)
            pending = ProposalsRepository(connection).get_pending_for_professor(professor_id)
        if pending is not None:
            raise PendingUpdateExistsError(pending.id)

    async def check(self, professor_id: int, job_id: str) -> tuple[bool, int | None]:
        with connect_database(self.database_path) as connection:
            current = ProfessorsRepository(connection).get(professor_id)
            if current is None:
                raise ProfessorNotFoundError(professor_id)
            current_publications = PublicationsRepository(connection).list_for_professor(
                professor_id
            )

        candidate = FacultyCandidate(
            name=current.name,
            title=current.title,
            email=current.email,
            official_profile_url=current.official_profile_url,
        )
        try:
            research = await self.researcher.research_with_refresh(candidate)
        except Exception as error:
            emit_professor_research_failed(candidate.name, error)
            raise
        emit_professor_extracted(candidate, research)
        difference = compare_professor_update(current, current_publications, research)
        if not difference.changed:
            return False, None

        proposal_input = ProposalCreate(
            job_id=job_id,
            professor_id=professor_id,
            old_values=difference.old_values.model_dump(mode="json"),
            new_values=difference.new_values.model_dump(mode="json"),
            publication_diff=difference.publication_diff.model_dump(mode="json"),
            source_urls=difference.new_values.source_urls,
            confidence=research.confidence,
        )
        try:
            with connect_database(self.database_path) as connection:
                proposal = ProposalsRepository(connection).create_pending(proposal_input)
        except sqlite3.IntegrityError as error:
            with connect_database(self.database_path) as connection:
                pending = ProposalsRepository(connection).get_pending_for_professor(professor_id)
            if pending is not None:
                raise PendingUpdateExistsError(pending.id) from error
            raise
        return True, proposal.id

    def list_proposals(
        self,
        *,
        status: ProposalStatus | None,
        professor_id: int | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ProposalRecord], int]:
        with connect_database(self.database_path) as connection:
            return ProposalsRepository(connection).list(
                status=status,
                professor_id=professor_id,
                page=page,
                page_size=page_size,
            )

    def get_proposal(self, proposal_id: int) -> ProposalRecord:
        with connect_database(self.database_path) as connection:
            proposal = ProposalsRepository(connection).get(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError(proposal_id)
        return proposal

    def apply(self, proposal_id: int) -> ProposalRecord:
        now = datetime.now(UTC)
        try:
            with connect_database(self.database_path) as connection, transaction(connection):
                proposals = ProposalsRepository(connection)
                proposal = proposals.get(proposal_id)
                if proposal is None:
                    raise ProposalNotFoundError(proposal_id)
                if proposal.status is not ProposalStatus.PENDING:
                    raise ProposalNotPendingError(proposal_id)

                values = ProfessorUpdateSnapshot.model_validate(proposal.new_values)
                publication_diff = PublicationDifference.model_validate(
                    proposal.publication_diff
                )
                professor = ProfessorCreate(**values.model_dump())
                updated = ProfessorsRepository(connection).update(
                    proposal.professor_id,
                    professor,
                    now=now,
                )
                if updated is None:
                    raise ProfessorNotFoundError(proposal.professor_id)
                publications = [
                    PublicationCreate(**item.model_dump())
                    for item in publication_diff.proposed
                ]
                PublicationsRepository(connection).replace_for_professor(
                    proposal.professor_id,
                    publications,
                    now=now,
                )
                resolved = proposals.mark_applied(proposal_id, resolved_at=now)
                if resolved is None:
                    raise ProposalNotPendingError(proposal_id)
                return resolved
        except (ProposalNotFoundError, ProposalNotPendingError, ProfessorNotFoundError):
            raise
        except Exception as error:
            raise ProposalApplyError(f"Failed to apply proposal {proposal_id}") from error

    def reject(self, proposal_id: int) -> ProposalRecord:
        with connect_database(self.database_path) as connection, transaction(connection):
            proposals = ProposalsRepository(connection)
            proposal = proposals.get(proposal_id)
            if proposal is None:
                raise ProposalNotFoundError(proposal_id)
            if proposal.status is not ProposalStatus.PENDING:
                raise ProposalNotPendingError(proposal_id)
            resolved = proposals.mark_rejected(proposal_id)
            if resolved is None:
                raise ProposalNotPendingError(proposal_id)
            return resolved
