"""Lab application tracking models."""

from datetime import date, datetime

from lab_tracker.models.common import ApplicationState, DomainModel


class ApplicationUpsert(DomainModel):
    state: ApplicationState
    application_date: date | None = None
    notes: str = ""


class ApplicationRecord(ApplicationUpsert):
    id: int
    professor_id: int
    updated_at: datetime
