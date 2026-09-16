"""Exercise orchestration with the real research graph and deterministic providers."""

import asyncio
import json

import httpx
import pytest
from langchain_core.messages import AIMessage

from lab_tracker.models.homepage import ReadWebpageResult
from lab_tracker.models.research import OpenAlexPublication
from lab_tracker.services import update_checks
from lab_tracker.services.discovery import FacultyCandidate
from lab_tracker.services.openalex_provider import AmbiguousOpenAlexAuthorError
from lab_tracker.services.research_graph import ResearchGraphError

OFFICIAL = "https://ece.illinois.edu/about/directory/faculty/alice"
PERSONAL = "https://alice.example.edu/research"
SUMMARY = "Alice Systems researches secure computing and reliable computer architecture."
TAGS = ["Security & Privacy", "Computer Architecture & Hardware"]


def pipeline(
    monkeypatch,
    *,
    personal=PERSONAL,
    failed_urls=(),
    invalid_summary=False,
    publication_error=None,
    match_identity=True,
):
    events = []
    captured = []
    papers = [
        OpenAlexPublication(
            source_id=f"openalex:W{i}",
            openalex_id=f"W{i}",
            title=f"Paper {i}",
            year=2026,
        )
        for i in range(1, 4)
    ]

    class Reader:
        async def extract(self, url):
            events.append(url)
            if url in failed_urls:
                raise httpx.ConnectError("unavailable")
            text = (
                SUMMARY if match_identity else "Other Person researches entirely different topics."
            )
            return ReadWebpageResult(requested_url=url, url=url, content=text)

        async def map(self, url, instructions):
            raise AssertionError("No Map expected")

    class Search:
        async def search(self, query):
            raise AssertionError("No Search expected")

    class Agent:
        def __init__(self, stage):
            self.stage = stage
            self.turn = 0

        async def ainvoke(self, messages):
            urls = [OFFICIAL, PERSONAL] if personal else [OFFICIAL]
            self.turn += 1
            if self.stage == "research":
                events.append("research_agent")
            if self.turn <= len(urls):
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_webpage",
                            "args": {"url": urls[self.turn - 1]},
                            "id": f"{self.stage}-{self.turn}",
                            "type": "tool_call",
                        }
                    ],
                )
            if self.stage == "homepage":
                events.append("homepage")
                return AIMessage(content=json.dumps({"personal_homepage_url": personal}))
            return AIMessage(content="Done")

    class Finalizer:
        async def ainvoke(self, messages):
            events.append("summary")
            payload = json.loads(messages[1].content)
            captured.append(payload)
            if not match_identity:
                return {"status": "insufficient_evidence", "reason": "Wrong person"}
            return {
                "status": "success",
                "research_summary": SUMMARY,
                "tags": ["invalid"] if invalid_summary else TAGS,
                "evidence_urls": [page["url"] for page in payload["pages"]],
            }

    class Model:
        def bind_tools(self, tools, **kwargs):
            names = {tool.name for tool in tools}
            assert names in ({"search_web", "read_webpage"}, {"read_webpage", "map_website"})
            return Agent("homepage" if "search_web" in names else "research")

        def with_structured_output(self, schema, **kwargs):
            return Finalizer()

    class Publications:
        async def get_recent_publications(self, identity):
            assert events[-1] == "summary"
            assert identity.name == "Alice Systems"
            events.append("publications")
            if publication_error:
                raise publication_error
            return papers

    researcher = update_checks.LangGraphCandidateResearcher(
        chat_model=Model(),
        tavily=Search(),
        openalex=Publications(),
        page_http=None,
        homepage_reader=Reader(),
    )
    candidate = FacultyCandidate(
        name="Alice Systems", title="Professor", email=None, official_profile_url=OFFICIAL
    )
    return researcher, candidate, events, captured, papers


@pytest.mark.asyncio
@pytest.mark.parametrize("refresh", [False, True])
@pytest.mark.parametrize(
    ("personal", "failed_urls", "expected_urls"),
    [
        (PERSONAL, (), [OFFICIAL, PERSONAL]),
        (None, (), [OFFICIAL]),
        (PERSONAL, (PERSONAL,), [OFFICIAL]),
        (PERSONAL, (OFFICIAL,), [PERSONAL]),
    ],
)
async def test_webpage_summary_precedes_all_publications(
    monkeypatch,
    refresh,
    personal,
    failed_urls,
    expected_urls,
):
    researcher, candidate, events, captured, papers = pipeline(
        monkeypatch,
        personal=personal,
        failed_urls=failed_urls,
    )
    run = researcher.research_with_refresh if refresh else researcher.research
    result = await run(candidate)
    assert events.index("homepage") < events.index("research_agent") < events.index("summary")
    assert events[-2:] == ["summary", "publications"]
    assert events.count(OFFICIAL) == 2
    assert [p["url"] for p in captured[0]["pages"]] == expected_urls
    assert "openalex_publications" not in captured[0]
    assert result.source_urls == expected_urls
    assert result.research_summary == SUMMARY
    assert result.tags == TAGS
    assert result.publications == papers  # Attach every result, without LLM selection.
    assert result.personal_homepage_url == (None if personal in failed_urls else personal)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"failed_urls": (OFFICIAL, PERSONAL)},
        {"invalid_summary": True},
        {"match_identity": False},
    ],
)
async def test_invalid_webpage_evidence_never_starts_publication_lookup(monkeypatch, kwargs):
    researcher, candidate, events, _, _ = pipeline(monkeypatch, **kwargs)
    with pytest.raises(ResearchGraphError):
        await researcher.research(candidate)
    expected = (
        2 if kwargs.get("invalid_summary") else 1 if kwargs.get("match_identity") is False else 0
    )
    assert events.count("summary") == expected
    assert "publications" not in events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        AmbiguousOpenAlexAuthorError("Multiple authors"),
        httpx.ConnectError("unavailable"),
        httpx.ReadTimeout("timed out"),
        ValueError("Malformed provider response"),
        RuntimeError("Unexpected provider failure"),
    ],
)
@pytest.mark.parametrize("refresh", [False, True])
async def test_publication_error_preserves_validated_research(monkeypatch, error, refresh):
    researcher, candidate, events, captured, _ = pipeline(monkeypatch, publication_error=error)
    run = researcher.research_with_refresh if refresh else researcher.research
    result = await run(candidate)
    assert result.research_summary == SUMMARY
    assert result.tags == TAGS
    assert result.personal_homepage_url == PERSONAL
    assert result.publications == []
    assert result.publications_unavailable is True
    assert events[-2:] == ["summary", "publications"]
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_publication_cancellation_still_cancels_research(monkeypatch):
    researcher, candidate, _, _, _ = pipeline(
        monkeypatch, publication_error=asyncio.CancelledError()
    )
    with pytest.raises(asyncio.CancelledError):
        await researcher.research_with_refresh(candidate)
