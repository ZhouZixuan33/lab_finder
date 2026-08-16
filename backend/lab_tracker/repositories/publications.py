"""Parameterized SQL access for professor publications."""

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime

from lab_tracker.models.publication import PublicationCreate, PublicationRecord


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _publication_from_row(row: sqlite3.Row) -> PublicationRecord:
    return PublicationRecord.model_validate(dict(row))


class PublicationsRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def list_for_professor(self, professor_id: int) -> list[PublicationRecord]:
        rows = self.connection.execute(
            """
            SELECT * FROM publications
            WHERE professor_id = ?
            ORDER BY year DESC, lower(title) ASC
            """,
            (professor_id,),
        ).fetchall()
        return [_publication_from_row(row) for row in rows]

    def create_many(
        self,
        professor_id: int,
        publications: Sequence[PublicationCreate],
        *,
        now: datetime | None = None,
    ) -> list[PublicationRecord]:
        created_at = _timestamp(now or datetime.now(UTC))
        for publication in publications:
            self.connection.execute(
                """
                INSERT INTO publications (
                    professor_id, title, year, venue, publication_url,
                    doi, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(professor_id, title, year) DO NOTHING
                """,
                (
                    professor_id,
                    publication.title,
                    publication.year,
                    publication.venue,
                    publication.publication_url,
                    publication.doi,
                    publication.source.value,
                    created_at,
                ),
            )
        return self.list_for_professor(professor_id)

    def delete_for_professor(self, professor_id: int) -> int:
        cursor = self.connection.execute(
            "DELETE FROM publications WHERE professor_id = ?",
            (professor_id,),
        )
        return cursor.rowcount

    def replace_for_professor(
        self,
        professor_id: int,
        publications: Sequence[PublicationCreate],
        *,
        now: datetime | None = None,
    ) -> list[PublicationRecord]:
        self.delete_for_professor(professor_id)
        return self.create_many(professor_id, publications, now=now)
