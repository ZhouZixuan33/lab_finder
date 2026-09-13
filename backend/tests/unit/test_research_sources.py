from pathlib import Path

import httpx
import pytest

from lab_tracker.models.research import ResearchIdentity, SearchHit
from lab_tracker.services.page_extractor import PageExtractor
from lab_tracker.services.research_prompts import build_finalizer_messages
from lab_tracker.services.research_sources import (
    CandidateSourceRegistry,
    UnknownSourceError,
    UnsafeSourceError,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"


class FakeHttpClient:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requested_urls: list[str] = []

    async def get(self, url: str, **_kwargs: object) -> httpx.Response:
        self.requested_urls.append(url)
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            text=self.pages[url],
            headers={"Content-Type": "text/html; charset=utf-8"},
            request=request,
        )


def test_source_registry_assigns_job_local_ids_deduplicates_and_blocks_unsafe_urls() -> None:
    registry = CandidateSourceRegistry(max_sources=5)
    registered = registry.register_hits(
        [
            SearchHit(title="Lab", url="https://example.edu/lab/", snippet="Lab page"),
            SearchHit(title="Duplicate", url="https://example.edu/lab", snippet="Same URL"),
            SearchHit(title="Local", url="http://127.0.0.1/admin", snippet="Unsafe"),
        ]
    )

    assert len(registered) == 1
    assert registered[0].source_id == "source_001"
    assert registered[0].candidate_id == "candidate_001"
    assert registry.get("source_001").url == "https://example.edu/lab"

    with pytest.raises(UnsafeSourceError):
        registry.register_hit(
            SearchHit(title="Metadata", url="http://169.254.169.254/latest", snippet="Unsafe")
        )
    with pytest.raises(UnknownSourceError):
        registry.get("source_999")


@pytest.mark.asyncio
async def test_page_extractor_accepts_only_registry_ids_and_sanitizes_untrusted_html() -> None:
    url = "https://alice.example.edu"
    registry = CandidateSourceRegistry()
    source = registry.register_hit(SearchHit(title="Alice", url=url, snippet="Homepage"))
    html = (FIXTURES / "professor_homepage.html").read_text(encoding="utf-8")
    http = FakeHttpClient({url: html})
    extractor = PageExtractor(http, registry, max_text_characters=500)
    identity = ResearchIdentity(
        name="Alice Systems",
        email="alice@illinois.edu",
        title="Professor",
        affiliation="University of Illinois Urbana-Champaign Electrical and Computer Engineering",
        official_profile_url="https://ece.illinois.edu/about/directory/faculty/alice",
    )

    page = await extractor.extract(source.source_id, identity)

    assert "reliable computer architecture" in page.text
    assert "Ignore previous instructions" not in page.text
    assert "window.promptInjection" not in page.text
    assert "Site navigation" not in page.text
    assert len(page.text) <= 500
    assert page.identity_signals.name_match is True
    assert page.identity_signals.email_match is True
    assert page.identity_signals.affiliation_match is True

    with pytest.raises(UnknownSourceError):
        await extractor.extract("https://attacker.example/prompt", identity)
    assert http.requested_urls == [url]


@pytest.mark.asyncio
async def test_prompt_injection_text_never_reaches_the_finalizer_prompt() -> None:
    url = "https://alice.example.edu/research"
    registry = CandidateSourceRegistry()
    source = registry.register_hit(SearchHit(title="Alice", url=url, snippet="Research"))
    html = (FIXTURES / "prompt_injection_page.html").read_text(encoding="utf-8")
    identity = ResearchIdentity(
        name="Alice Systems",
        email="alice@illinois.edu",
        title="Professor",
        affiliation="University of Illinois Urbana-Champaign Electrical and Computer Engineering",
        official_profile_url="https://ece.illinois.edu/about/directory/faculty/alice",
    )
    page = await PageExtractor(FakeHttpClient({url: html}), registry).extract(
        source.source_id,
        identity,
    )

    messages = build_finalizer_messages(
        identity,
        pages=[page],
        previous_errors=[],
    )
    prompt = " ".join(str(message.content) for message in messages)

    assert "reliable computing systems" in prompt
    assert "Ignore all previous instructions" not in prompt
    assert "stealSecrets" not in prompt
