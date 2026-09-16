import json
import sqlite3

import pytest

from lab_tracker.db.connection import connect_database
from lab_tracker.db.migrations import DEFAULT_MIGRATIONS_DIRECTORY, MigrationError, run_migrations
from lab_tracker.services.diff import ProfessorUpdateSnapshot

OFFICIAL = "https://ece.illinois.edu/about/directory/faculty/aschwing"
PERSONAL = "https://www.alexander-schwing.de"


def legacy(connection, homepage=PERSONAL, lab=PERSONAL):
    for filename in ("001_initial.sql", "002_prospective_students.sql"):
        connection.executescript((DEFAULT_MIGRATIONS_DIRECTORY / filename).read_text())
    connection.execute("PRAGMA user_version = 2")
    connection.execute(
        "INSERT INTO professors (id,name,title,directory_profile_url,homepage_url,lab_url,"
        "research_summary,source_hash,created_at,last_checked_at,updated_at) "
        "VALUES (75,'Alexander Schwing','Professor',?,?,?,'Research','hash',"
        "'2026-09-15','2026-09-15','2026-09-15')",
        (OFFICIAL, homepage, lab),
    )


def test_schwing_and_pending_proposal_preserve_personal_url_with_backup(tmp_path):
    path = tmp_path / "tracker.db"
    with connect_database(path) as c:
        legacy(c)
        snapshot = dict(c.execute("SELECT * FROM professors").fetchone())
        snapshot = {
            k: snapshot[k]
            for k in (
                "name",
                "title",
                "directory_profile_url",
                "homepage_url",
                "lab_url",
                "research_summary",
                "source_hash",
            )
        }
        proposed = {**snapshot, "homepage_url": OFFICIAL}
        c.execute(
            "INSERT INTO update_proposals (job_id,professor_id,status,old_values_json,"
            "new_values_json,created_at) VALUES ('job',75,'pending',?,?,'2026-09-15')",
            (json.dumps(snapshot), json.dumps(proposed)),
        )
        assert run_migrations(c) == [3]
        row = dict(c.execute("SELECT * FROM professors").fetchone())
        assert row["official_profile_url"] == OFFICIAL
        assert row["personal_homepage_url"] == PERSONAL
        assert not {"homepage_url", "lab_url", "directory_profile_url"} & row.keys()
        proposal = c.execute("SELECT * FROM update_proposals").fetchone()
        assert proposal["status"] == "pending"
        for key in ("old_values_json", "new_values_json"):
            value = ProfessorUpdateSnapshot.model_validate_json(proposal[key])
            assert value.personal_homepage_url == PERSONAL
            assert value.official_profile_url == OFFICIAL
        assert not c.execute("PRAGMA foreign_key_check").fetchall()
        assert run_migrations(c) == []
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] == 2
        assert c.execute("SELECT homepage_url FROM professors").fetchone()[0] == PERSONAL


@pytest.mark.parametrize(
    "home,lab,expected",
    [
        (PERSONAL, None, PERSONAL),
        (OFFICIAL, None, None),
        (PERSONAL, OFFICIAL, PERSONAL),
        (None, PERSONAL, PERSONAL),
    ],
)
def test_fallback_never_uses_official_profile_as_personal(tmp_path, home, lab, expected):
    with connect_database(tmp_path / "tracker.db") as c:
        legacy(c, home, lab)
        run_migrations(c)
        assert c.execute("SELECT personal_homepage_url FROM professors").fetchone()[0] == expected


def test_conflicting_personal_urls_stop_before_schema_change(tmp_path):
    with connect_database(tmp_path / "tracker.db") as c:
        legacy(c, PERSONAL, "https://different.example.edu")
        with pytest.raises(MigrationError, match="Professor 75"):
            run_migrations(c)
        assert c.execute("PRAGMA user_version").fetchone()[0] == 2
        assert c.execute("SELECT homepage_url FROM professors").fetchone()[0] == PERSONAL
