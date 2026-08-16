"""Validated domain models used by repositories and API schemas."""

from lab_tracker.models.application import ApplicationRecord, ApplicationUpsert
from lab_tracker.models.common import ApplicationState, ProposalStatus
from lab_tracker.models.professor import (
    ProfessorCreate,
    ProfessorDetail,
    ProfessorListItem,
    ProfessorRecord,
    TagCount,
)
from lab_tracker.models.publication import PublicationCreate, PublicationRecord
from lab_tracker.models.update import ProposalCreate, ProposalRecord

__all__ = [
    "ApplicationRecord",
    "ApplicationState",
    "ApplicationUpsert",
    "ProfessorCreate",
    "ProfessorDetail",
    "ProfessorListItem",
    "ProfessorRecord",
    "ProposalCreate",
    "ProposalRecord",
    "ProposalStatus",
    "PublicationCreate",
    "PublicationRecord",
    "TagCount",
]
