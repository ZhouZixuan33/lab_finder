from pathlib import Path

from lab_tracker.db.connection import connect_database
from lab_tracker.db.migrations import DEFAULT_MIGRATIONS_DIRECTORY, run_migrations
from lab_tracker.models.professor import ProfessorCreate
from lab_tracker.models.research import ValidatedProfessorResearch
from lab_tracker.models.update import ProposalCreate
from lab_tracker.repositories.professors import ProfessorsRepository
from lab_tracker.repositories.proposals import ProposalsRepository
from lab_tracker.services.diff import compare_professor_update
from lab_tracker.services.updates import ProfessorUpdateService


def test_legacy_migration_and_recruitment_proposal_round_trip(tmp_path: Path):
    database = tmp_path / "prospective.db"
    with connect_database(database) as connection:
        connection.executescript(
            (DEFAULT_MIGRATIONS_DIRECTORY / "001_initial.sql").read_text(encoding="utf-8")
            + "\nPRAGMA user_version = 1;"
        )
        connection.execute(
            "INSERT INTO professors (name, title, directory_profile_url, research_summary, "
            "source_hash, created_at, last_checked_at, updated_at) "
            "VALUES ('Alice', 'Professor', 'https://example.edu/alice', 'Research', "
            "'hash', '2026-09-14', '2026-09-14', '2026-09-14')"
        )
        connection.commit()
        assert run_migrations(connection) == [2, 3]
        repository = ProfessorsRepository(connection)
        current = repository.list_all()[0]
        assert current.prospective_students_quote is None
        research = ValidatedProfessorResearch(
            research_summary=current.research_summary,
            tags=[],
            prospective_students_quote="Prospective students are welcome to apply.",
            prospective_students_source_url=current.official_profile_url,
        )
        difference = compare_professor_update(current, [], research)
        assert "prospective_students_quote" in difference.field_changes
        proposal = ProposalsRepository(connection).create_pending(ProposalCreate(
            job_id="prospective-check", professor_id=current.id,
            old_values=difference.old_values.model_dump(mode="json"),
            new_values=difference.new_values.model_dump(mode="json"),
            publication_diff=difference.publication_diff.model_dump(mode="json"),
        ))
    ProfessorUpdateService(database, None).apply(proposal.id)
    with connect_database(database) as connection:
        repository = ProfessorsRepository(connection)
        detail = repository.get_detail(current.id)
        items, _ = repository.list()
        assert items[0].prospective_students_quote == research.prospective_students_quote
        assert detail.prospective_students_source_url == current.official_profile_url
        copy_values = difference.new_values.model_dump()
        copy_values["official_profile_url"] = "https://example.edu/another-professor"
        copied = repository.create(ProfessorCreate(**copy_values))
        assert copied.prospective_students_quote == research.prospective_students_quote
