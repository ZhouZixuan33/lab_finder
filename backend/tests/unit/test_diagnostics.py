import io
import json
import logging

from lab_tracker.diagnostics import (
    LOGGER_NAME,
    configure_application_logging,
    emit_professor_extracted,
    emit_professor_research_failed,
)
from lab_tracker.models.research import OpenAlexPublication, ValidatedProfessorResearch
from lab_tracker.services.discovery import FacultyCandidate


def candidate() -> FacultyCandidate:
    return FacultyCandidate(
        name="Alice Systems",
        title="Professor",
        email="alice@illinois.edu",
        official_profile_url="https://ece.illinois.edu/alice",
    )


def research() -> ValidatedProfessorResearch:
    return ValidatedProfessorResearch(
        research_summary="Alice studies dependable computer systems and reliable accelerators.",
        tags=["Architecture", "Reliable AI"],
        personal_homepage_url="https://alice.example.edu/lab",
        publications=[
            OpenAlexPublication(
                source_id="openalex:W1",
                openalex_id="W1",
                title="Reliable Accelerators",
                year=2026,
                venue="ExampleConf",
                publication_url="https://openalex.org/W1",
            )
        ],
        source_urls=["https://alice.example.edu/lab"],
        confidence=0.92,
    )


def test_terminal_logging_configuration_is_idempotent() -> None:
    application_logger = logging.getLogger("lab_tracker")
    original_handlers = list(application_logger.handlers)
    original_level = application_logger.level
    original_propagate = application_logger.propagate
    stream = io.StringIO()
    try:
        application_logger.handlers.clear()
        configure_application_logging(stream=stream)
        configure_application_logging(stream=stream)

        logging.getLogger(LOGGER_NAME).info("test.event {}")

        assert len(application_logger.handlers) == 1
        assert stream.getvalue().count("test.event") == 1
    finally:
        application_logger.handlers[:] = original_handlers
        application_logger.setLevel(original_level)
        application_logger.propagate = original_propagate


def test_extracted_professor_is_allowlisted_structured_json(caplog) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        emit_professor_extracted(candidate(), research())

    message = next(
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("professor.extracted ")
    )
    payload = json.loads(message.split(" ", 1)[1])
    assert payload == {
        "confidence": 0.92,
        "email": "alice@illinois.edu",
        "personal_homepage_url": "https://alice.example.edu/lab",
        "name": "Alice Systems",
        "publications": [
            {
                "publication_url": "https://openalex.org/W1",
                "title": "Reliable Accelerators",
                "venue": "ExampleConf",
                "year": 2026,
            }
        ],
        "research_summary": (
            "Alice studies dependable computer systems and reliable accelerators."
        ),
        "source_urls": ["https://alice.example.edu/lab"],
        "tags": ["Architecture", "Reliable AI"],
        "title": "Professor",
    }


def test_failure_event_never_serializes_exception_message(caplog) -> None:
    secret = "AIza-provider-secret"
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        emit_professor_research_failed("Alice Systems", RuntimeError(secret))

    output = "\n".join(record.getMessage() for record in caplog.records)
    assert "professor.research_failed" in output
    assert '"error_type":"RuntimeError"' in output
    assert secret not in output
