"""Exercise orchestration with the real research graph and deterministic providers."""

import asyncio
import json

import httpx
import pytest
from langchain_core.messages import AIMessage

from lab_tracker.models.research import OpenAlexPublication, ProfessorResearchResult
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

    class Homepage:
        def __init__(self, **kwargs):
            pass

        async def ainvoke(self):
            events.append("homepage")
            return personal

    class Http:
        async def get(self, url):
            events.append(url)
            if url in failed_urls:
                raise httpx.ConnectError("unavailable", request=httpx.Request("GET", url))
            text = (
                SUMMARY if match_identity else "Other Person researches entirely different topics."
            )
            return httpx.Response(
                200, request=httpx.Request("GET", url), text=f"<main>{text}</main>"
            )

    class Search:
        async def search(self, query):
            raise AssertionError("Sufficient homepage evidence should not require search")

    class Agent:
        async def ainvoke(self, messages):
            events.append("research_agent")
            return AIMessage(content="Website evidence is sufficient; finalize.")

    class Finalizer:
        async def ainvoke(self, messages):
            events.append("summary")
            # Retry prompts append errors after the JSON; this model intentionally
            # returns invalid IDs on every attempt for the failure test.
            payload, _ = json.JSONDecoder().raw_decode(str(messages[1].content))
            captured.append(payload)
            ids = [p["source_id"] for p in payload["verified_pages"]]
            if invalid_summary or not ids:
                ids = ["source_999"]
            return {
                "research_summary": SUMMARY,
                "tags": TAGS,
                "evidence_source_ids": ids,
                "homepage_source_id": ids[0],
            }

    class Model:
        def bind_tools(self, tools, **kwargs):
            assert {tool.name for tool in tools} == {
                "search_professor_web",
                "extract_candidate_page",
            }
            return Agent()

        def with_structured_output(self, schema):
            assert schema is ProfessorResearchResult
            return Finalizer()

    class Publications:
        async def get_recent_publications(self, identity):
            assert events[-1] == "summary"
            assert identity.name == "Alice Systems"
            events.append("publications")
            if publication_error:
                raise publication_error
            return papers

    monkeypatch.setattr(update_checks, "HomepageGraph", Homepage)
    researcher = update_checks.LangGraphCandidateResearcher(
        chat_model=Model(),
        tavily=Search(),
        openalex=Publications(),
        page_http=Http(),
        homepage_reader=None,
    )
    candidate = FacultyCandidate(
        name="Alice Systems", title="Professor", email=None, directory_profile_url=OFFICIAL
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
    attempted_urls = [OFFICIAL, PERSONAL] if personal else [OFFICIAL]
    assert events == ["homepage", *attempted_urls, "research_agent", "summary", "publications"]
    assert [p["url"] for p in captured[0]["verified_pages"]] == expected_urls
    assert "openalex_publications" not in captured[0]
    assert result.source_urls == expected_urls
    assert result.research_summary == SUMMARY
    assert result.tags == TAGS
    assert result.publications == papers  # Attach every result, without LLM selection.
    assert result.lab_url == personal


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
    assert events.count("summary") == 3
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
    assert result.lab_url == PERSONAL
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
