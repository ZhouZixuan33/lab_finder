import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from lab_tracker.db.connection import connect_database, transaction
from lab_tracker.db.migrations import run_migrations


@contextmanager
def migrated_database(database_path: Path) -> Iterator[sqlite3.Connection]:
    with connect_database(database_path) as connection:
        run_migrations(connection)
        yield connection


def insert_professor(
    connection: sqlite3.Connection,
    *,
    name: str = "Jane Example",
    profile_url: str = "https://ece.illinois.edu/example",
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO professors (
            name, title, email, official_profile_url, research_summary,
            source_hash, created_at, last_checked_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            "Professor",
            "jane@example.edu",
            profile_url,
            "Research summary",
            "source-hash",
            "2026-08-16T00:00:00Z",
            "2026-08-16T00:00:00Z",
            "2026-08-16T00:00:00Z",
        ),
    )
    return int(cursor.lastrowid)


def test_application_state_and_one_row_per_professor_are_enforced(tmp_path: Path) -> None:
    with migrated_database(tmp_path / "constraints.db") as connection:
        professor_id = insert_professor(connection)
        second_professor_id = insert_professor(
            connection,
            name="John Example",
            profile_url="https://ece.illinois.edu/second-example",
        )
        connection.execute(
            """
            INSERT INTO application_status (professor_id, state, updated_at)
            VALUES (?, ?, ?)
            """,
            (professor_id, "interested", "2026-08-16T00:00:00Z"),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO application_status (professor_id, state, updated_at)
                VALUES (?, ?, ?)
                """,
                (second_professor_id, "unknown", "2026-08-16T00:00:00Z"),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO application_status (professor_id, state, updated_at)
                VALUES (?, ?, ?)
                """,
                (professor_id, "applied", "2026-08-16T00:00:00Z"),
            )


def test_publication_unique_constraint_and_cascade_are_enforced(tmp_path: Path) -> None:
    with migrated_database(tmp_path / "publications.db") as connection:
        professor_id = insert_professor(connection)
        publication = (
            professor_id,
            "A Useful Paper",
            2026,
            "openalex",
            "2026-08-16T00:00:00Z",
        )
        connection.execute(
            """
            INSERT INTO publications (professor_id, title, year, source, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            publication,
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO publications (professor_id, title, year, source, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                publication,
            )

        connection.execute("DELETE FROM professors WHERE id = ?", (professor_id,))
        remaining = connection.execute(
            "SELECT COUNT(*) FROM publications WHERE professor_id = ?", (professor_id,)
        ).fetchone()[0]

    assert remaining == 0


def test_proposal_status_confidence_and_one_pending_rule_are_enforced(tmp_path: Path) -> None:
    with migrated_database(tmp_path / "proposals.db") as connection:
        professor_id = insert_professor(connection)
        proposal_values = (
            "job-one",
            professor_id,
            "pending",
            "{}",
            "{}",
            0.8,
            "2026-08-16T00:00:00Z",
        )
        connection.execute(
            """
            INSERT INTO update_proposals (
                job_id, professor_id, status, old_values_json,
                new_values_json, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            proposal_values,
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO update_proposals (
                    job_id, professor_id, status, old_values_json,
                    new_values_json, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("job-two", professor_id, "pending", "{}", "{}", 0.9, "2026-08-16"),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO update_proposals (
                    job_id, professor_id, status, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("job-three", professor_id, "failed", 0.5, "2026-08-16"),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO update_proposals (
                    job_id, professor_id, status, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("job-four", professor_id, "rejected", 1.01, "2026-08-16"),
            )

        connection.execute(
            """
            UPDATE update_proposals
            SET status = 'applied', resolved_at = ?
            WHERE job_id = ?
            """,
            ("2026-08-16T00:01:00Z", "job-one"),
        )
        connection.execute(
            """
            INSERT INTO update_proposals (job_id, professor_id, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("job-five", professor_id, "pending", "2026-08-16T00:02:00Z"),
        )

        pending_count = connection.execute(
            """
            SELECT COUNT(*) FROM update_proposals
            WHERE professor_id = ? AND status = 'pending'
            """,
            (professor_id,),
        ).fetchone()[0]

    assert pending_count == 1


def test_professor_and_publications_roll_back_as_one_unit(tmp_path: Path) -> None:
    with migrated_database(tmp_path / "rollback.db") as connection:
        with pytest.raises(sqlite3.IntegrityError), transaction(connection):
            professor_id = insert_professor(connection)
            connection.execute(
                """
                INSERT INTO publications (
                    professor_id, title, year, source, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (professor_id, None, 2026, "openalex", "2026-08-16T00:00:00Z"),
            )

        professor_count = connection.execute("SELECT COUNT(*) FROM professors").fetchone()[0]
        publication_count = connection.execute("SELECT COUNT(*) FROM publications").fetchone()[0]

    assert professor_count == 0
    assert publication_count == 0
