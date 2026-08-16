"""Application-status service isolated from professor research writes."""

from datetime import datetime
from pathlib import Path

from lab_tracker.db.connection import connect_database
from lab_tracker.errors import ProfessorNotFoundError
from lab_tracker.models.application import ApplicationRecord, ApplicationUpsert
from lab_tracker.repositories.applications import ApplicationsRepository
from lab_tracker.repositories.professors import ProfessorsRepository


class ApplicationService:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def upsert(
        self,
        professor_id: int,
        application: ApplicationUpsert,
        *,
        now: datetime | None = None,
    ) -> ApplicationRecord:
        with connect_database(self.database_path) as connection:
            if ProfessorsRepository(connection).get(professor_id) is None:
                raise ProfessorNotFoundError(professor_id)
            return ApplicationsRepository(connection).upsert(
                professor_id,
                application,
                now=now,
            )

    def delete(self, professor_id: int) -> None:
        with connect_database(self.database_path) as connection:
            if ProfessorsRepository(connection).get(professor_id) is None:
                raise ProfessorNotFoundError(professor_id)
            ApplicationsRepository(connection).delete(professor_id)
