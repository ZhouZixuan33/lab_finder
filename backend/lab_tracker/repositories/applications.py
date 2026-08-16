"""Parameterized SQL access for application tracking records."""

import sqlite3
from datetime import UTC, datetime

from lab_tracker.models.application import ApplicationRecord, ApplicationUpsert


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _application_from_row(row: sqlite3.Row) -> ApplicationRecord:
    return ApplicationRecord.model_validate(dict(row))


class ApplicationsRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def get(self, professor_id: int) -> ApplicationRecord | None:
        row = self.connection.execute(
            "SELECT * FROM application_status WHERE professor_id = ?",
            (professor_id,),
        ).fetchone()
        return _application_from_row(row) if row is not None else None

    def upsert(
        self,
        professor_id: int,
        application: ApplicationUpsert,
        *,
        now: datetime | None = None,
    ) -> ApplicationRecord:
        updated_at = now or datetime.now(UTC)
        application_date = (
            application.application_date.isoformat() if application.application_date else None
        )
        self.connection.execute(
            """
            INSERT INTO application_status (
                professor_id, state, application_date, notes, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(professor_id) DO UPDATE SET
                state = excluded.state,
                application_date = excluded.application_date,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (
                professor_id,
                application.state.value,
                application_date,
                application.notes,
                _timestamp(updated_at),
            ),
        )
        record = self.get(professor_id)
        if record is None:  # pragma: no cover - guarded by INSERT success
            raise RuntimeError("Application upsert did not return a row")
        return record

    def delete(self, professor_id: int) -> bool:
        cursor = self.connection.execute(
            "DELETE FROM application_status WHERE professor_id = ?",
            (professor_id,),
        )
        return cursor.rowcount > 0
