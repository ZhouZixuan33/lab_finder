"""Parameterized SQL access for the professor catalog."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime

from lab_tracker.models.common import ApplicationState
from lab_tracker.models.professor import (
    ProfessorCreate,
    ProfessorDetail,
    ProfessorListItem,
    ProfessorRecord,
    TagCount,
)
from lab_tracker.repositories.applications import ApplicationsRepository
from lab_tracker.repositories.proposals import ProposalsRepository
from lab_tracker.repositories.publications import PublicationsRepository

SORT_COLUMNS = {
    "name": "lower(p.name)",
    "title": "lower(p.title)",
    "updated_at": "p.updated_at",
    "state": "coalesce(a.state, '')",
}
SORT_ORDERS = {"asc": "ASC", "desc": "DESC"}


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _professor_from_row(row: sqlite3.Row) -> ProfessorRecord:
    values = dict(row)
    values["tags"] = json.loads(values.pop("tags_json"))
    values["source_urls"] = json.loads(values.pop("source_urls_json"))
    return ProfessorRecord.model_validate(values)


def _list_item_from_row(row: sqlite3.Row) -> ProfessorListItem:
    values = dict(row)
    values["tags"] = json.loads(values.pop("tags_json"))
    return ProfessorListItem.model_validate(values)


class ProfessorsRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(
        self,
        professor: ProfessorCreate,
        *,
        now: datetime | None = None,
    ) -> ProfessorRecord:
        timestamp = _timestamp(now or datetime.now(UTC))
        cursor = self.connection.execute(
            """
            INSERT INTO professors (
                name, title, email, directory_profile_url, homepage_url, lab_url,
                research_summary, tags_json, source_urls_json, source_hash,
                created_at, last_checked_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                professor.name,
                professor.title,
                professor.email,
                professor.directory_profile_url,
                professor.homepage_url,
                professor.lab_url,
                professor.research_summary,
                _json(professor.tags),
                _json(professor.source_urls),
                professor.source_hash,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        record = self.get(int(cursor.lastrowid))
        if record is None:  # pragma: no cover - guarded by INSERT success
            raise RuntimeError("Professor insert did not return a row")
        return record

    def get(self, professor_id: int) -> ProfessorRecord | None:
        row = self.connection.execute(
            "SELECT * FROM professors WHERE id = ?",
            (professor_id,),
        ).fetchone()
        return _professor_from_row(row) if row is not None else None

    def list_all(self) -> list[ProfessorRecord]:
        rows = self.connection.execute(
            "SELECT * FROM professors ORDER BY id ASC"
        ).fetchall()
        return [_professor_from_row(row) for row in rows]

    def list(
        self,
        *,
        search: str | None = None,
        tags: Sequence[str] = (),
        state: ApplicationState | str | None = None,
        page: int = 1,
        page_size: int = 25,
        sort: str = "name",
        order: str = "asc",
    ) -> tuple[list[ProfessorListItem], int]:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("Invalid professor pagination")
        if sort not in SORT_COLUMNS:
            raise ValueError(f"Unsupported professor sort: {sort}")
        if order not in SORT_ORDERS:
            raise ValueError(f"Unsupported professor sort order: {order}")

        normalized_state: ApplicationState | None = None
        if state is not None:
            try:
                normalized_state = ApplicationState(state)
            except ValueError as error:
                raise ValueError(f"Unsupported application state: {state}") from error

        conditions: list[str] = []
        parameters: list[object] = []
        if search and search.strip():
            pattern = f"%{_escape_like(search.strip().lower())}%"
            conditions.append(
                """
                (
                    lower(p.name) LIKE ? ESCAPE '\\'
                    OR lower(p.title) LIKE ? ESCAPE '\\'
                    OR lower(coalesce(p.email, '')) LIKE ? ESCAPE '\\'
                    OR EXISTS (
                        SELECT 1 FROM json_each(p.tags_json) AS search_tag
                        WHERE lower(CAST(search_tag.value AS TEXT)) LIKE ? ESCAPE '\\'
                    )
                )
                """
            )
            parameters.extend([pattern, pattern, pattern, pattern])

        normalized_tags = sorted({tag.strip().lower() for tag in tags if tag.strip()})
        if normalized_tags:
            placeholders = ", ".join("?" for _ in normalized_tags)
            conditions.append(
                f"""
                EXISTS (
                    SELECT 1 FROM json_each(p.tags_json) AS filter_tag
                    WHERE lower(trim(CAST(filter_tag.value AS TEXT))) IN ({placeholders})
                )
                """
            )
            parameters.extend(normalized_tags)

        if normalized_state is not None:
            conditions.append("a.state = ?")
            parameters.append(normalized_state.value)

        where_sql = " AND ".join(f"({condition.strip()})" for condition in conditions)
        if where_sql:
            where_sql = f"WHERE {where_sql}"

        from_sql = (
            "FROM professors AS p "
            "LEFT JOIN application_status AS a ON a.professor_id = p.id"
        )
        total = self.connection.execute(
            f"SELECT COUNT(*) {from_sql} {where_sql}",
            parameters,
        ).fetchone()[0]
        rows = self.connection.execute(
            f"""
            SELECT
                p.id, p.name, p.title, p.email, p.directory_profile_url,
                p.homepage_url, p.lab_url, p.tags_json, p.updated_at,
                a.state AS application_state
            {from_sql}
            {where_sql}
            ORDER BY {SORT_COLUMNS[sort]} {SORT_ORDERS[order]}, p.id ASC
            LIMIT ? OFFSET ?
            """,
            [*parameters, page_size, (page - 1) * page_size],
        ).fetchall()
        return [_list_item_from_row(row) for row in rows], int(total)

    def get_detail(self, professor_id: int) -> ProfessorDetail | None:
        professor = self.get(professor_id)
        if professor is None:
            return None

        application = ApplicationsRepository(self.connection).get(professor_id)
        publications = PublicationsRepository(self.connection).list_for_professor(professor_id)
        pending = ProposalsRepository(self.connection).get_pending_for_professor(professor_id)
        return ProfessorDetail(
            **professor.model_dump(),
            publications=publications,
            application=application,
            pending_proposal_id=pending.id if pending else None,
        )

    def list_tags(self) -> list[TagCount]:
        rows = self.connection.execute(
            """
            SELECT
                lower(trim(CAST(tag.value AS TEXT))) AS tag,
                COUNT(DISTINCT p.id) AS professor_count
            FROM professors AS p
            JOIN json_each(p.tags_json) AS tag
            WHERE tag.type = 'text' AND trim(CAST(tag.value AS TEXT)) <> ''
            GROUP BY lower(trim(CAST(tag.value AS TEXT)))
            ORDER BY professor_count DESC, tag ASC
            """
        ).fetchall()
        return [TagCount.model_validate(dict(row)) for row in rows]
