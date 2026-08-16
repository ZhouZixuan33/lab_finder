"""Sanitized HTML extraction for registry-approved research sources."""

import re
from typing import Protocol

from bs4 import BeautifulSoup, Tag
from httpx import Response

from lab_tracker.models.research import ExtractedPage, IdentitySignals, ResearchIdentity
from lab_tracker.services.identity import normalize_email, normalize_name
from lab_tracker.services.research_sources import CandidateSourceRegistry

PROMPT_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "system prompt",
    "you are chatgpt",
    "reveal your instructions",
    "assistant:",
)
REMOVED_TAGS = (
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "footer",
    "form",
    "iframe",
    "svg",
    "template",
)


class PageHttpClient(Protocol):
    async def get(self, url: str, **kwargs: object) -> Response: ...


class PageExtractor:
    def __init__(
        self,
        http_client: PageHttpClient,
        registry: CandidateSourceRegistry,
        *,
        max_text_characters: int = 12_000,
    ) -> None:
        if max_text_characters < 100:
            raise ValueError("Extracted page limit must be at least 100 characters")
        self.http_client = http_client
        self.registry = registry
        self.max_text_characters = max_text_characters

    async def extract(
        self,
        source_id: str,
        identity: ResearchIdentity,
    ) -> ExtractedPage:
        source = self.registry.get(source_id)
        response = await self.http_client.get(source.url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        page_title = self._title(soup)

        for element in soup.find_all(REMOVED_TAGS):
            element.decompose()
        for element in soup.find_all(["aside", "p", "pre", "code", "blockquote", "div"]):
            if not isinstance(element, Tag):
                continue
            direct_strings = element.find_all(string=True, recursive=False)
            text = " ".join(value.strip() for value in direct_strings).casefold()
            if any(marker in text for marker in PROMPT_INJECTION_MARKERS):
                element.decompose()

        content_root = soup.find("main") or soup.find("article") or soup.body or soup
        text = re.sub(r"\s+", " ", " ".join(content_root.stripped_strings)).strip()
        text = text[: self.max_text_characters]
        normalized_text = normalize_name(text)
        normalized_email = normalize_email(identity.email)
        text_casefolded = text.casefold()
        signals = IdentitySignals(
            name_match=normalize_name(identity.name) in normalized_text,
            email_match=bool(normalized_email and normalized_email in text_casefolded),
            affiliation_match=(
                "university of illinois" in text_casefolded or "uiuc" in text_casefolded
            ),
        )
        return ExtractedPage(
            source_id=source.source_id,
            candidate_id=source.candidate_id,
            url=source.url,
            title=page_title,
            text=text,
            identity_signals=signals,
        )

    @staticmethod
    def _title(soup: BeautifulSoup) -> str | None:
        if soup.title:
            value = " ".join(soup.title.stripped_strings).strip()
            if value:
                return value[:300]
        heading = soup.find("h1")
        if heading:
            value = " ".join(heading.stripped_strings).strip()
            return value[:300] or None
        return None
