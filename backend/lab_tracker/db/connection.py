"""SQLite connection lifecycle and explicit transaction management."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

BUSY_TIMEOUT_MILLISECONDS = 5_000
TRANSACTION_MODES = frozenset({"DEFERRED", "IMMEDIATE", "EXCLUSIVE"})


@contextmanager
def connect_database(database_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Open a configured SQLite connection and always close it on exit."""

    path = Path(database_path)
    if str(database_path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        str(path),
        timeout=BUSY_TIMEOUT_MILLISECONDS / 1_000,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MILLISECONDS}")
        connection.execute("PRAGMA journal_mode = WAL")
        yield connection
    finally:
        connection.close()


@contextmanager
def transaction(
    connection: sqlite3.Connection,
    *,
    mode: str = "IMMEDIATE",
) -> Iterator[sqlite3.Connection]:
    """Run a unit of work in one explicit SQLite transaction."""

    normalized_mode = mode.upper()
    if normalized_mode not in TRANSACTION_MODES:
        raise ValueError(f"Unsupported SQLite transaction mode: {mode}")
    if connection.in_transaction:
        raise RuntimeError("Nested transactions are not supported")

    connection.execute(f"BEGIN {normalized_mode}")
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
