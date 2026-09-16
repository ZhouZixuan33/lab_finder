"""UIUC faculty-directory parsing and pre-research candidate filtering."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, replace
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from lab_tracker.services.http import RateLimitedHttpClient
from lab_tracker.services.identity import (
    UIUC_ECE_AFFILIATION,
    AmbiguousIdentityError,
    IdentityIndex,
    normalize_email,
    normalize_url,
)

FACULTY_DIRECTORY_URL = "https://ece.illinois.edu/about/directory/faculty-dept"
FACULTY_PROFILE_PATH = re.compile(r"^/about/directory/faculty/[^/]+/?$")
EXCLUDED_TITLE_MARKERS = ("teaching", "lecturer", "instructor", "emeritus", "adjunct")
RESEARCH_EVIDENCE_MARKERS = (
    "research areas",
    "research interests",
    "research statement",
    "research group",
    "laboratory",
)
TITLE_MARKERS = ("professor", "lecturer", "instructor", "emeritus", "adjunct", "department head")

@dataclass(frozen=True)
class FacultyCandidate:
    name: str
    title: str
    email: str | None
    official_profile_url: str
    affiliation: str = UIUC_ECE_AFFILIATION
    has_research_evidence: bool = False


@dataclass(frozen=True)
class CandidateFailure:
    candidate: FacultyCandidate
    error_code: str
    message: str


@dataclass(frozen=True)
class CandidateResearchBatch[ResearchResult]:
    results: list[ResearchResult]
    existing_count: int
    failures: list[CandidateFailure]


def is_research_active_title(title: str) -> bool | None:
    normalized = " ".join(title.casefold().split())
    if any(marker in normalized for marker in EXCLUDED_TITLE_MARKERS):
        return False
    if "professor" in normalized:
        return True
    return None


def _card_for_anchor(anchor: Tag) -> Tag | None:
    semantic_parent = anchor.find_parent(["article", "li"])
    if isinstance(semantic_parent, Tag):
        return semantic_parent

    for parent in anchor.parents:
        if not isinstance(parent, Tag) or parent.name not in {"div", "section"}:
            continue
        text = " ".join(parent.stripped_strings).casefold()
        if len(text) <= 1_000 and any(marker in text for marker in TITLE_MARKERS):
            return parent
    return None


def _title_from_card(card: Tag, name: str) -> str | None:
    preferred = card.select_one("[class*='title'], [class*='position'], [class*='role']")
    if preferred is not None:
        value = " ".join(preferred.stripped_strings).strip()
        if value:
            return value

    for value in (" ".join(text.split()) for text in card.stripped_strings):
        normalized = value.casefold()
        is_title = any(marker in normalized for marker in TITLE_MARKERS)
        if value != name and len(value) <= 180 and is_title:
            return value
    return None


def _email_from_document(document: Tag | BeautifulSoup) -> str | None:
    mail_link = document.select_one("a[href^='mailto:' i]")
    if mail_link is not None:
        return normalize_email(mail_link.get("href"))
    text = " ".join(document.stripped_strings)
    match = re.search(r"[A-Z0-9._%+-]+@illinois\.edu", text, flags=re.IGNORECASE)
    return normalize_email(match.group(0)) if match else None


def parse_faculty_directory(
    html: str,
    *,
    base_url: str = FACULTY_DIRECTORY_URL,
) -> list[FacultyCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[FacultyCandidate] = []
    seen_urls: set[str] = set()

    for anchor in soup.select("a[href]"):
        raw_href = anchor.get("href")
        if not isinstance(raw_href, str):
            continue
        profile_url = normalize_url(urljoin(base_url, raw_href))
        if FACULTY_PROFILE_PATH.fullmatch(urlsplit(profile_url).path) is None:
            continue
        if profile_url in seen_urls:
            continue

        name = " ".join(anchor.stripped_strings).strip()
        card = _card_for_anchor(anchor)
        if not name or card is None:
            continue
        title = _title_from_card(card, name)
        if not title:
            continue

        candidates.append(
            FacultyCandidate(
                name=name,
                title=title,
                email=_email_from_document(card),
                official_profile_url=profile_url,
            )
        )
        seen_urls.add(profile_url)

    return candidates


def enrich_candidate_from_profile(candidate: FacultyCandidate, html: str) -> FacultyCandidate:
    soup = BeautifulSoup(html, "html.parser")
    visible_text = " ".join(soup.stripped_strings).casefold()
    has_evidence = any(marker in visible_text for marker in RESEARCH_EVIDENCE_MARKERS)
    return replace(
        candidate,
        email=candidate.email or _email_from_document(soup),
        has_research_evidence=has_evidence,
    )


class FacultyDiscoveryClient:
    def __init__(self, http_client: RateLimitedHttpClient) -> None:
        self.http_client = http_client

    async def discover(self) -> list[FacultyCandidate]:
        directory_html = await self.http_client.get_text(FACULTY_DIRECTORY_URL)
        discovered = parse_faculty_directory(directory_html)
        accepted: list[FacultyCandidate] = []

        for candidate in discovered:
            title_status = is_research_active_title(candidate.title)
            if title_status is False:
                continue
            enriched = candidate
            if candidate.email is None or title_status is None:
                profile_html = await self.http_client.get_text(candidate.official_profile_url)
                enriched = enrich_candidate_from_profile(candidate, profile_html)
            if title_status is True or enriched.has_research_evidence:
                accepted.append(enriched)
        return accepted


async def research_new_candidates[ResearchResult](
    candidates: Iterable[FacultyCandidate],
    identities: IdentityIndex,
    research_provider: Callable[[FacultyCandidate], Awaitable[ResearchResult]],
) -> CandidateResearchBatch[ResearchResult]:
    """Invoke expensive research only after deterministic existing-record checks."""

    results: list[ResearchResult] = []
    failures: list[CandidateFailure] = []
    existing_count = 0

    for candidate in candidates:
        try:
            existing_professor_id = identities.match(candidate)
        except AmbiguousIdentityError as error:
            failures.append(
                CandidateFailure(
                    candidate=candidate,
                    error_code="AMBIGUOUS_IDENTITY",
                    message=str(error),
                )
            )
            continue

        if existing_professor_id is not None:
            existing_count += 1
            continue

        try:
            results.append(await research_provider(candidate))
        except Exception as error:  # noqa: BLE001 - one candidate must not abort the batch
            failures.append(
                CandidateFailure(
                    candidate=candidate,
                    error_code="RESEARCH_FAILED",
                    message=str(error),
                )
            )

    return CandidateResearchBatch(
        results=results,
        existing_count=existing_count,
        failures=failures,
    )
