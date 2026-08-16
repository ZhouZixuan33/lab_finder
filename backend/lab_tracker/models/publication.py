"""Professor publication models."""

from datetime import datetime

from pydantic import Field

from lab_tracker.models.common import DomainModel, PublicationSource


class PublicationCreate(DomainModel):
    title: str = Field(min_length=1)
    year: int
    venue: str | None = None
    publication_url: str | None = None
    doi: str | None = None
    source: PublicationSource


class PublicationRecord(PublicationCreate):
    id: int
    professor_id: int
    created_at: datetime
