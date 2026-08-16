"""Semantic comparison for single-professor update proposals."""

import hashlib
import json
import re
from typing import Any

from pydantic import Field

from lab_tracker.models.common import DomainModel, PublicationSource
from lab_tracker.models.professor import ProfessorRecord
from lab_tracker.models.publication import PublicationRecord
from lab_tracker.models.research import ValidatedProfessorResearch
from lab_tracker.services.identity import normalize_email, normalize_url


class ProfessorUpdateSnapshot(DomainModel):
    name: str
    title: str
    email: str | None = None
    directory_profile_url: str
    homepage_url: str | None = None
    lab_url: str | None = None
    research_summary: str
    tags: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    source_hash: str


class PublicationUpdateSnapshot(DomainModel):
    title: str
    year: int
    venue: str | None = None
    publication_url: str | None = None
    doi: str | None = None
    source: PublicationSource


class PublicationDifference(DomainModel):
    added: list[PublicationUpdateSnapshot] = Field(default_factory=list)
    removed: list[PublicationUpdateSnapshot] = Field(default_factory=list)
    proposed: list[PublicationUpdateSnapshot] = Field(default_factory=list)


class ProfessorDifference(DomainModel):
    changed: bool
    old_values: ProfessorUpdateSnapshot
    new_values: ProfessorUpdateSnapshot
    field_changes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    publication_diff: PublicationDifference


def _publication_from_record(publication: PublicationRecord) -> PublicationUpdateSnapshot:
    return PublicationUpdateSnapshot(
        title=publication.title,
        year=publication.year,
        venue=publication.venue,
        publication_url=publication.publication_url,
        doi=publication.doi,
        source=publication.source,
    )


def _publication_key(publication: PublicationUpdateSnapshot) -> tuple[object, ...]:
    return (
        re.sub(r"\W+", " ", publication.title.casefold()).strip(),
        publication.year,
        (publication.venue or "").casefold(),
        normalize_url(publication.publication_url) if publication.publication_url else "",
        (publication.doi or "").casefold(),
        publication.source.value,
    )


def _semantic_hash(
    snapshot: ProfessorUpdateSnapshot,
    publications: list[PublicationUpdateSnapshot],
) -> str:
    payload = snapshot.model_dump(mode="json", exclude={"source_hash"})
    payload["tags"] = sorted({tag.casefold() for tag in snapshot.tags})
    payload["source_urls"] = sorted(
        {normalize_url(url) for url in snapshot.source_urls}
    )
    payload["publications"] = sorted(_publication_key(item) for item in publications)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _comparison_value(field: str, value: Any) -> Any:
    if field == "email":
        return normalize_email(value)
    if field in {"directory_profile_url", "homepage_url", "lab_url"}:
        return normalize_url(value) if value else None
    if field == "tags":
        return sorted({" ".join(tag.split()).casefold() for tag in value})
    if field == "source_urls":
        return sorted({normalize_url(url) for url in value})
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def compare_professor_update(
    current: ProfessorRecord,
    current_publications: list[PublicationRecord],
    research: ValidatedProfessorResearch,
) -> ProfessorDifference:
    old_values = ProfessorUpdateSnapshot(
        name=current.name,
        title=current.title,
        email=current.email,
        directory_profile_url=current.directory_profile_url,
        homepage_url=current.homepage_url,
        lab_url=current.lab_url,
        research_summary=current.research_summary,
        tags=current.tags,
        source_urls=current.source_urls,
        source_hash=current.source_hash,
    )
    proposed_publications = [
        PublicationUpdateSnapshot(
            title=publication.title,
            year=publication.year,
            venue=publication.venue,
            publication_url=publication.publication_url,
            doi=publication.doi,
            source=PublicationSource.OPENALEX,
        )
        for publication in research.publications
    ]
    proposed_sources = list(
        dict.fromkeys([current.directory_profile_url, *research.source_urls])
    )
    new_values_without_hash = ProfessorUpdateSnapshot(
        name=current.name,
        title=current.title,
        email=current.email,
        directory_profile_url=current.directory_profile_url,
        homepage_url=research.homepage_url,
        lab_url=research.lab_url,
        research_summary=research.research_summary,
        tags=research.tags,
        source_urls=proposed_sources,
        source_hash="pending",
    )
    new_values = new_values_without_hash.model_copy(
        update={
            "source_hash": _semantic_hash(
                new_values_without_hash,
                proposed_publications,
            )
        }
    )

    field_changes: dict[str, dict[str, Any]] = {}
    for field in (
        "name",
        "title",
        "email",
        "directory_profile_url",
        "homepage_url",
        "lab_url",
        "research_summary",
        "tags",
        "source_urls",
    ):
        old_value = getattr(old_values, field)
        new_value = getattr(new_values, field)
        if _comparison_value(field, old_value) != _comparison_value(field, new_value):
            field_changes[field] = {"old": old_value, "new": new_value}

    old_publications = [_publication_from_record(item) for item in current_publications]
    old_by_key = {_publication_key(item): item for item in old_publications}
    new_by_key = {_publication_key(item): item for item in proposed_publications}
    added = [new_by_key[key] for key in sorted(new_by_key.keys() - old_by_key.keys())]
    removed = [old_by_key[key] for key in sorted(old_by_key.keys() - new_by_key.keys())]
    publication_diff = PublicationDifference(
        added=added,
        removed=removed,
        proposed=sorted(
            proposed_publications,
            key=lambda item: (-item.year, item.title.casefold()),
        ),
    )
    return ProfessorDifference(
        changed=bool(field_changes or added or removed),
        old_values=old_values,
        new_values=new_values,
        field_changes=field_changes,
        publication_diff=publication_diff,
    )
