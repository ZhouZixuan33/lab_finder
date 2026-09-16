"""Professor catalog input and output models."""

from datetime import datetime

from pydantic import Field

from lab_tracker.models.application import ApplicationRecord
from lab_tracker.models.common import ApplicationState, DomainModel
from lab_tracker.models.publication import PublicationRecord


class ProfessorCreate(DomainModel):
    name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    email: str | None = None
    official_profile_url: str = Field(min_length=1)
    personal_homepage_url: str | None = None
    prospective_students_quote: str | None = None
    prospective_students_source_url: str | None = None
    research_summary: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    source_hash: str = Field(min_length=1)


class ProfessorRecord(ProfessorCreate):
    id: int
    created_at: datetime
    last_checked_at: datetime
    updated_at: datetime


class ProfessorListItem(DomainModel):
    id: int
    name: str
    title: str
    email: str | None
    official_profile_url: str
    personal_homepage_url: str | None
    prospective_students_quote: str | None = None
    prospective_students_source_url: str | None = None
    tags: list[str]
    application_state: ApplicationState | None = None
    updated_at: datetime


class ProfessorDetail(ProfessorRecord):
    publications: list[PublicationRecord] = Field(default_factory=list)
    application: ApplicationRecord | None = None
    pending_proposal_id: int | None = None


class TagCount(DomainModel):
    tag: str
    professor_count: int = Field(ge=1)
