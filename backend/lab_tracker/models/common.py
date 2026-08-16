"""Shared enums and base model configuration."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ApplicationState(StrEnum):
    INTERESTED = "interested"
    APPLIED = "applied"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"


class PublicationSource(StrEnum):
    FACULTY_PAGE = "faculty_page"
    LAB_PAGE = "lab_page"
    OPENALEX = "openalex"
