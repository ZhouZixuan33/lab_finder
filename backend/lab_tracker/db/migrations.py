"""Numbered raw-SQL migration runner backed by ``PRAGMA user_version``."""

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

MIGRATION_FILENAME = re.compile(r"^(?P<version>[0-9]+)_[a-z0-9_]+\.sql$")
DEFAULT_MIGRATIONS_DIRECTORY = Path(__file__).with_name("migrations")


class MigrationError(RuntimeError):
    """Raised when migration files are invalid or cannot be applied safely."""


@dataclass(frozen=True)
class Migration:
    version: int
    path: Path


def discover_migrations(directory: Path = DEFAULT_MIGRATIONS_DIRECTORY) -> list[Migration]:
    """Return validated migration files ordered by numeric version."""

    migrations: list[Migration] = []
    for path in directory.glob("*.sql"):
        match = MIGRATION_FILENAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"Invalid migration filename: {path.name}")
        version = int(match.group("version"))
        if version < 1:
            raise MigrationError(f"Migration version must be positive: {path.name}")
        migrations.append(Migration(version=version, path=path))

    migrations.sort(key=lambda migration: migration.version)
    versions = [migration.version for migration in migrations]
    if len(versions) != len(set(versions)):
        raise MigrationError("Migration versions must be unique")
    if versions and versions != list(range(1, versions[-1] + 1)):
        raise MigrationError("Migration versions must form a continuous sequence starting at 1")
    return migrations


def get_user_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def run_migrations(
    connection: sqlite3.Connection,
    directory: Path = DEFAULT_MIGRATIONS_DIRECTORY,
) -> list[int]:
    """Apply every migration newer than the database's user version."""

    current_version = get_user_version(connection)
    migrations = discover_migrations(directory)
    latest_version = migrations[-1].version if migrations else 0
    if current_version > latest_version:
        raise MigrationError(
            f"Database version {current_version} is newer than "
            f"available migrations {latest_version}"
        )

    applied_versions: list[int] = []
    for migration in migrations:
        if migration.version <= current_version:
            continue

        if migration.path.name == "003_profile_urls.sql":
            from lab_tracker.db.profile_urls import prepare_profile_url_migration

            try:
                prepare_profile_url_migration(connection)
            except ValueError as error:
                raise MigrationError(str(error)) from error

        sql = migration.path.read_text(encoding="utf-8")
        script = (
            "BEGIN IMMEDIATE;\n"
            f"{sql}\n"
            f"PRAGMA user_version = {migration.version};\n"
            "COMMIT;"
        )
        try:
            connection.executescript(script)
        except sqlite3.Error as error:
            if connection.in_transaction:
                connection.rollback()
            raise MigrationError(
                f"Failed to apply migration {migration.path.name}"
            ) from error

        applied_versions.append(migration.version)
        current_version = migration.version

    return applied_versions
