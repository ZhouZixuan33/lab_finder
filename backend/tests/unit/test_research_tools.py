from typing import Any

import pytest
from pydantic import SecretStr

from lab_tracker.models.research import (
    ExtractedPage,
    IdentitySignals,
    OpenAlexPublication,
    ResearchIdentity,
)
from lab_tracker.services.rate_limit import SerialRateLimiter
from lab_tracker.services.research_sources import CandidateSourceRegistry
from lab_tracker.services.research_tools import create_research_tools
from lab_tracker.services.tavily_provider import TavilyProvider


class FakeTavilyBackend:
    def __init__(self) -> None:
        self.inputs: list[dict[str, Any]] = []

    async def ainvoke(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        self.inputs.append(tool_input)
        return {
            "answer": "must not escape",
            "images": ["must not escape"],
            "results": [
                {
                    "title": f"Result {index}",
                    "url": f"https://example.edu/{index}",
                    "content": f"Snippet {index}",
                    "raw_content": "must not escape",
                    "score": 0.9,
                }
                for index in range(7)
            ],
        }


class FakePageExtractor:
    async def extract(self, source_id: str, _identity: ResearchIdentity) -> ExtractedPage:
        return ExtractedPage(
            source_id=source_id,
            candidate_id="candidate_001",
            url="https://example.edu/0",
            title="Example",
            text="Verified research page.",
            identity_signals=IdentitySignals(name_match=True),
        )


class FakeOpenAlexProvider:
    async def get_recent_publications(
        self,
        _identity: ResearchIdentity,
    ) -> list[OpenAlexPublication]:
        return [
            OpenAlexPublication(
                source_id="openalex:W1",
                openalex_id="W1",
                title="Recent Paper",
                year=2026,
                venue="ExampleConf",
                publication_url="https://openalex.org/W1",
                cited_by_count=3,
            )
        ]


@pytest.mark.asyncio
async def test_tavily_provider_returns_only_five_sanitized_basic_results() -> None:
    backend = FakeTavilyBackend()
    provider = TavilyProvider(
        backend,
        limiter=SerialRateLimiter(1.0),
        api_key=SecretStr("tavily-secret"),
    )

    results = await provider.search("Alice Systems UIUC lab")
    serialized = repr(results)

    assert backend.inputs == [{"query": "Alice Systems UIUC lab"}]
    assert len(results) == 5
    assert results[0].snippet == "Snippet 0"
    assert "raw_content" not in serialized
    assert "must not escape" not in serialized
    assert "tavily-secret" not in repr(provider)
    assert "tavily-secret" not in serialized


@pytest.mark.asyncio
async def test_langchain_tools_expose_only_bounded_model_arguments() -> None:
    identity = ResearchIdentity(
        name="Alice Systems",
        email="alice@illinois.edu",
        title="Professor",
        affiliation="University of Illinois Urbana-Champaign Electrical and Computer Engineering",
        official_profile_url="https://ece.illinois.edu/about/directory/faculty/alice",
    )
    registry = CandidateSourceRegistry()
    tavily = TavilyProvider(FakeTavilyBackend(), limiter=SerialRateLimiter(1.0))
    tools = create_research_tools(
        identity=identity,
        registry=registry,
        tavily=tavily,
        page_extractor=FakePageExtractor(),
        openalex=FakeOpenAlexProvider(),
    )
    tools_by_name = {tool.name: tool for tool in tools}

    assert set(tools_by_name) == {
        "search_professor_web",
        "extract_candidate_page",
        "get_recent_publications",
    }
    search_schema = tools_by_name["search_professor_web"].args_schema.model_json_schema()
    page_schema = tools_by_name["extract_candidate_page"].args_schema.model_json_schema()
    publications_schema = tools_by_name[
        "get_recent_publications"
    ].args_schema.model_json_schema()
    assert set(search_schema["properties"]) == {"query"}
    assert set(page_schema["properties"]) == {"source_id"}
    assert publications_schema["properties"] == {}

    search_result = await tools_by_name["search_professor_web"].ainvoke(
        {"query": "Alice Systems UIUC lab"}
    )
    page_result = await tools_by_name["extract_candidate_page"].ainvoke(
        {"source_id": search_result[0]["source_id"]}
    )
    publications_result = await tools_by_name["get_recent_publications"].ainvoke({})

    assert search_result[0]["url"] == "https://example.edu/0"
    assert page_result["text"] == "Verified research page."
    assert publications_result[0]["title"] == "Recent Paper"
