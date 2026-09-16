import sqlite3
from pathlib import Path

from lab_tracker.db.connection import connect_database
from lab_tracker.db.migrations import run_migrations

EXPECTED_TABLES = {
    "application_status",
    "professors",
    "publications",
    "update_proposals",
}


def test_initial_migration_builds_the_complete_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "lab_tracker.db"

    with connect_database(database_path) as connection:
        applied_versions = run_migrations(connection)
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert applied_versions == [1, 2, 3]
    assert {row["name"] for row in table_rows} == EXPECTED_TABLES
    assert user_version == 3


def test_running_migrations_twice_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "lab_tracker.db"

    with connect_database(database_path) as connection:
        assert run_migrations(connection) == [1, 2, 3]
        schema_before = connection.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()

        assert run_migrations(connection) == []
        schema_after = connection.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()

    assert [tuple(row) for row in schema_after] == [tuple(row) for row in schema_before]


def test_connection_factory_applies_required_sqlite_pragmas(tmp_path: Path) -> None:
    with connect_database(tmp_path / "lab_tracker.db") as connection:
        row = connection.execute("SELECT 42 AS answer").fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]

    assert isinstance(row, sqlite3.Row)
    assert row["answer"] == 42
    assert foreign_keys == 1
    assert journal_mode == "wal"
    assert busy_timeout == 5_000
