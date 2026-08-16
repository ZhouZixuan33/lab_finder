"""Read-only professor catalog service."""

from collections.abc import Sequence
from pathlib import Path

from lab_tracker.db.connection import connect_database
from lab_tracker.errors import ProfessorNotFoundError
from lab_tracker.models.common import ApplicationState
from lab_tracker.models.professor import ProfessorDetail, ProfessorListItem, TagCount
from lab_tracker.repositories.professors import ProfessorsRepository


class CatalogService:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def list_professors(
        self,
        *,
        search: str | None,
        tags: Sequence[str],
        state: ApplicationState | None,
        page: int,
        page_size: int,
        sort: str,
        order: str,
    ) -> tuple[list[ProfessorListItem], int]:
        with connect_database(self.database_path) as connection:
            return ProfessorsRepository(connection).list(
                search=search,
                tags=tags,
                state=state,
                page=page,
                page_size=page_size,
                sort=sort,
                order=order,
            )

    def get_professor(self, professor_id: int) -> ProfessorDetail:
        with connect_database(self.database_path) as connection:
            detail = ProfessorsRepository(connection).get_detail(professor_id)
        if detail is None:
            raise ProfessorNotFoundError(professor_id)
        return detail

    def list_tags(self) -> list[TagCount]:
        with connect_database(self.database_path) as connection:
            return ProfessorsRepository(connection).list_tags()
