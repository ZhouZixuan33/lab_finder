"""Raw SQL repositories."""

from lab_tracker.repositories.applications import ApplicationsRepository
from lab_tracker.repositories.professors import ProfessorsRepository
from lab_tracker.repositories.proposals import ProposalsRepository
from lab_tracker.repositories.publications import PublicationsRepository

__all__ = [
    "ApplicationsRepository",
    "ProfessorsRepository",
    "ProposalsRepository",
    "PublicationsRepository",
]
