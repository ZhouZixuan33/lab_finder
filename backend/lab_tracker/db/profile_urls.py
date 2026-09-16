"""One-time, loss-aware conversion of legacy profile fields and proposal snapshots."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from lab_tracker.services.identity import normalize_url


def select_personal_url(official, homepage, lab):
    def key(value):
        return normalize_url(value).split("://", 1)[-1] if value and value.strip() else None

    official_key = key(official)
    home = homepage if key(homepage) and key(homepage) != official_key else None
    personal = lab if key(lab) and key(lab) != official_key else None
    if home and personal and key(home) != key(personal):
        raise ValueError(f"Conflicting personal URLs: {home!r} and {personal!r}")
    return personal or home


def convert_snapshot(raw):
    if raw is None:
        return None
    values = json.loads(raw)
    if not isinstance(values, dict):
        raise ValueError("Proposal snapshot must be an object")
    official = values.pop("directory_profile_url", values.get("official_profile_url"))
    personal = select_personal_url(
        official,
        values.pop("homepage_url", None),
        values.pop("lab_url", values.get("personal_homepage_url")),
    )
    values.update(official_profile_url=official, personal_homepage_url=personal)
    return json.dumps(values, ensure_ascii=False)


def prepare_profile_url_migration(connection: sqlite3.Connection) -> Path | None:
    # Validate all records before backup/DDL; fail with the offending record ID.
    for row in connection.execute(
        "SELECT id, directory_profile_url, homepage_url, lab_url FROM professors"
    ):
        try:
            select_personal_url(*row[1:])
        except ValueError as error:
            raise ValueError(f"Professor {row[0]}: {error}") from error
    for row in connection.execute(
        "SELECT id, old_values_json, new_values_json FROM update_proposals"
    ):
        try:
            convert_snapshot(row[1])
            convert_snapshot(row[2])
        except ValueError as error:
            raise ValueError(f"Proposal {row[0]}: {error}") from error

    filename = connection.execute("PRAGMA database_list").fetchone()[2]
    backup = None
    if filename:
        source = Path(filename)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = source.with_name(
            f"{source.name}.before-profile-urls-{stamp}-{uuid4().hex[:8]}.bak"
        )
        with sqlite3.connect(backup) as target:
            connection.backup(target)
    connection.create_function("select_personal_url", 3, select_personal_url)
    connection.create_function("convert_profile_snapshot", 1, convert_snapshot)
    return backup
