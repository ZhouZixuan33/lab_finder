"""Safe, structured terminal diagnostics for professor research."""

import json
import logging
import sys
from typing import Any, TextIO

from lab_tracker.models.research import ValidatedProfessorResearch
from lab_tracker.services.discovery import FacultyCandidate

LOGGER_NAME = "lab_tracker.research"
_HANDLER_MARKER = "_lab_tracker_terminal_handler"


def configure_application_logging(*, stream: TextIO | None = None) -> None:
    """Configure one application-owned terminal handler without touching Uvicorn logs."""

    application_logger = logging.getLogger("lab_tracker")
    if not any(getattr(handler, _HANDLER_MARKER, False) for handler in application_logger.handlers):
        handler = logging.StreamHandler(stream or sys.stderr)
        setattr(handler, _HANDLER_MARKER, True)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        application_logger.addHandler(handler)
    application_logger.setLevel(logging.INFO)
    application_logger.propagate = False


def emit_research_event(event: str, **fields: Any) -> None:
    """Emit a compact JSON event; diagnostic failures never affect research."""

    try:
        payload = json.dumps(
            fields,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        logging.getLogger(LOGGER_NAME).info("%s %s", event, payload)
    except Exception:  # noqa: BLE001 - logging must never break the job
        return


def emit_professor_extracted(
    candidate: FacultyCandidate,
    research: ValidatedProfessorResearch,
) -> None:
    """Print the allowlisted, validated professor payload."""

    emit_research_event(
        "professor.extracted",
        name=candidate.name,
        title=candidate.title,
        email=candidate.email,
        homepage_url=research.homepage_url,
        lab_url=research.lab_url,
        research_summary=research.research_summary,
        tags=research.tags,
        publications=[
            {
                "title": publication.title,
                "year": publication.year,
                "venue": publication.venue,
                "publication_url": publication.publication_url,
            }
            for publication in research.publications
        ],
        source_urls=research.source_urls,
        confidence=research.confidence,
    )


def emit_professor_research_failed(professor: str, error: Exception) -> None:
    """Report a failed candidate without serializing a credential-bearing message."""

    emit_research_event(
        "professor.research_failed",
        professor=professor,
        error_type=type(error).__name__,
    )
