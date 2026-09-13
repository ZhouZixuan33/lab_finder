import json
import logging
from collections import deque
from collections.abc import Sequence
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage, BaseMessage

from lab_tracker.diagnostics import LOGGER_NAME
from lab_tracker.models.research import (
    ExtractedPage,
    IdentitySignals,
    ProfessorResearchResult,
    ResearchIdentity,
    SearchHit,
)
from lab_tracker.services.research_graph import ProfessorResearchGraph, ResearchGraphError
from lab_tracker.services.research_sources import CandidateSourceRegistry
from lab_tracker.services.research_tools import create_research_tools


def tool_call(name: str, arguments: dict[str, object], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": arguments, "id": call_id, "type": "tool_call"}],
    )


class FakeRunnable:
    def __init__(self, outputs: deque[Any], captured_inputs: list[Any]) -> None:
        self.outputs = outputs
        self.captured_inputs = captured_inputs

    async def ainvoke(self, value: Any) -> Any:
        self.captured_inputs.append(value)
        output = self.outputs.popleft()
        if isinstance(output, Exception):
            raise output
        return output


class FakeChatModel:
    def __init__(
        self,
        *,
        agent_outputs: Sequence[AIMessage],
        finalizer_outputs: Sequence[object],
    ) -> None:
        self.agent_outputs = deque(agent_outputs)
        self.finalizer_outputs = deque(finalizer_outputs)
        self.agent_inputs: list[list[BaseMessage]] = []
        self.finalizer_inputs: list[list[BaseMessage]] = []
        self.bound_tool_names: list[str] = []
        self.parallel_tool_calls: bool | None = None
        self.structured_schema: object | None = None

    def bind_tools(self, tools: Sequence[object], **kwargs: object) -> FakeRunnable:
        self.bound_tool_names = [str(cast(Any, tool).name) for tool in tools]
        self.parallel_tool_calls = kwargs.get("parallel_tool_calls")  # type: ignore[assignment]
        return FakeRunnable(self.agent_outputs, self.agent_inputs)

    def with_structured_output(self, schema: object) -> FakeRunnable:
        self.structured_schema = schema
        return FakeRunnable(self.finalizer_outputs, self.finalizer_inputs)


class FakeSearchProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str) -> list[SearchHit]:
        self.queries.append(query)
        slug = len(self.queries)
        return [
            SearchHit(
                title=f"Alice Lab {slug}",
                url=f"https://alice.example.edu/lab-{slug}",
                snippet="Reliable systems laboratory.",
            )
        ]


class FakePageExtractor:
    def __init__(self, registry: CandidateSourceRegistry) -> None:
        self.registry = registry
        self.source_ids: list[str] = []

    async def extract(
        self,
        source_id: str,
        _identity: ResearchIdentity,
    ) -> ExtractedPage:
        self.source_ids.append(source_id)
        source = self.registry.get(source_id)
        return ExtractedPage(
            source_id=source.source_id,
            candidate_id=source.candidate_id,
            url=source.url,
            title=source.title,
            text="Alice Systems at UIUC researches reliable computing systems.",
            identity_signals=IdentitySignals(name_match=True, affiliation_match=True),
        )


def identity() -> ResearchIdentity:
    return ResearchIdentity(
        name="Alice Systems",
        email="alice@illinois.edu",
        title="Professor",
        affiliation="University of Illinois Urbana-Champaign Electrical and Computer Engineering",
        official_profile_url="https://ece.illinois.edu/about/directory/faculty/alice",
    )


def final_result(
    *,
    evidence_source_id: str = "source_002",
    homepage_source_id: str | None = "source_002",
) -> dict[str, object]:
    return {
        "research_summary": (
            "Alice Systems researches reliable computer architecture and secure accelerators."
        ),
        "tags": [
            "Security & Privacy",
            "Computer Architecture & Systems",
        ],
        "homepage_source_id": homepage_source_id,
        "evidence_source_ids": [evidence_source_id],
        "confidence": 0.9,
    }


def build_graph(
    model: FakeChatModel,
) -> tuple[ProfessorResearchGraph, FakeSearchProvider, FakePageExtractor]:
    professor_identity = identity()
    registry = CandidateSourceRegistry()
    search = FakeSearchProvider()
    pages = FakePageExtractor(registry)
    tools = create_research_tools(
        identity=professor_identity,
        registry=registry,
        tavily=search,
        page_extractor=pages,
    )
    graph = ProfessorResearchGraph(
        identity=professor_identity,
        chat_model=model,
        tools=tools,
        registry=registry,
    )
    return graph, search, pages


@pytest.mark.asyncio
async def test_graph_runs_explicit_tool_sequence_and_structured_finalizer() -> None:
    model = FakeChatModel(
        agent_outputs=[
            tool_call("search_professor_web", {"query": "Alice Systems UIUC lab"}, "call-1"),
            tool_call("extract_candidate_page", {"source_id": "source_002"}, "call-2"),
            tool_call("get_recent_publications", {}, "call-3"),
            AIMessage(content="Evidence is sufficient."),
        ],
        finalizer_outputs=[final_result()],
    )
    graph, search, pages = build_graph(model)

    result = await graph.ainvoke()

    assert search.queries == ["Alice Systems UIUC lab"]
    assert pages.source_ids == ["source_002"]
    assert result.homepage_url == "https://alice.example.edu/lab-1"
    assert result.publications == []
    assert any("UNKNOWN_TOOL" in str(m.content) for ms in model.agent_inputs for m in ms)
    assert model.parallel_tool_calls is False
    assert model.structured_schema is ProfessorResearchResult
    assert set(model.bound_tool_names) == {
        "search_professor_web",
        "extract_candidate_page",
    }


@pytest.mark.asyncio
async def test_graph_allows_search_rewrite_but_enforces_three_search_budget() -> None:
    model = FakeChatModel(
        agent_outputs=[
            tool_call("search_professor_web", {"query": "query one"}, "call-1"),
            tool_call("search_professor_web", {"query": "query two"}, "call-2"),
            tool_call("search_professor_web", {"query": "query three"}, "call-3"),
            tool_call("search_professor_web", {"query": "query four"}, "call-4"),
            tool_call("extract_candidate_page", {"source_id": "source_002"}, "call-5"),
            tool_call("get_recent_publications", {}, "call-6"),
            AIMessage(content="Stop and finalize."),
        ],
        finalizer_outputs=[final_result()],
    )
    graph, search, pages = build_graph(model)

    result = await graph.ainvoke()

    assert search.queries == ["query one", "query two", "query three"]
    assert pages.source_ids == ["source_002"]
    assert result.research_summary.startswith("Alice Systems")
    guard_errors = [
        message
        for invocation in model.agent_inputs
        for message in invocation
        if (
            getattr(message, "type", None) == "tool"
            and "TOOL_BUDGET_EXCEEDED" in str(message.content)
        )
    ]
    assert guard_errors


@pytest.mark.asyncio
async def test_graph_rejects_arbitrary_url_and_parallel_tool_calls_before_toolnode() -> None:
    model = FakeChatModel(
        agent_outputs=[
            tool_call("browse_any_url", {"url": "https://attacker.example"}, "call-0"),
            tool_call(
                "search_professor_web",
                {"query": "Alice Systems", "professor_name": "Different Person"},
                "call-override",
            ),
            tool_call(
                "extract_candidate_page",
                {"source_id": "https://attacker.example/prompt"},
                "call-1",
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_professor_web",
                        "args": {"query": "one"},
                        "id": "call-2",
                        "type": "tool_call",
                    },
                    {
                        "name": "get_recent_publications",
                        "args": {},
                        "id": "call-3",
                        "type": "tool_call",
                    },
                ],
            ),
            tool_call("extract_candidate_page", {"source_id": "source_001"}, "call-4"),
            AIMessage(content="Finalize."),
        ],
        finalizer_outputs=[
            final_result(
                evidence_source_id="source_001",
                homepage_source_id="source_001",
            )

        ],
    )
    graph, search, pages = build_graph(model)

    result = await graph.ainvoke()

    assert search.queries == []
    assert pages.source_ids == ["source_001"]
    assert result.homepage_url == identity().official_profile_url


@pytest.mark.asyncio
async def test_finalizer_retries_twice_then_accepts_valid_structure() -> None:
    model = FakeChatModel(
        agent_outputs=[
            tool_call("search_professor_web", {"query": "Alice Systems"}, "call-1"),
            tool_call("extract_candidate_page", {"source_id": "source_002"}, "call-2"),
            AIMessage(content="Finalize."),
        ],
        finalizer_outputs=[
            final_result()
            | {"tags": ["Congestion Control"]},
            final_result(evidence_source_id="source_999"),
            final_result(),
        ],
    )
    graph, _search, _pages = build_graph(model)

    result = await graph.ainvoke()

    assert result.tags == [
        "Security & Privacy",
        "Computer Architecture & Systems",
    ]
    assert len(model.finalizer_inputs) == 3
    retry_prompt = " ".join(
        str(message.content) for message in model.finalizer_inputs[1]
    )
    assert "controlled taxonomy" in retry_prompt


@pytest.mark.asyncio
async def test_finalizer_fails_after_three_invalid_attempts() -> None:
    model = FakeChatModel(
        agent_outputs=[AIMessage(content="Finalize without evidence.")],
        finalizer_outputs=[final_result(), final_result(), final_result()],
    )
    graph, _search, _pages = build_graph(model)

    with pytest.raises(ResearchGraphError, match="evidence"):
        await graph.ainvoke()

    assert len(model.finalizer_inputs) == 3


@pytest.mark.asyncio
async def test_graph_logs_real_agent_and_finalizer_invocation_boundaries(caplog) -> None:
    model = FakeChatModel(
        agent_outputs=[
            tool_call("extract_candidate_page", {"source_id": "source_001"}, "call-1"),
            AIMessage(content="Finalize."),
        ],
        finalizer_outputs=[
            final_result(
                evidence_source_id="source_001",
                homepage_source_id="source_001",
            )

        ],
    )
    graph, _search, _pages = build_graph(model)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        await graph.ainvoke()

    output = "\n".join(record.getMessage() for record in caplog.records)
    assert 'llm_call.started {"attempt":1,"phase":"research_agent"' in output
    assert 'llm_call.completed {"attempt":1,"duration_ms":' in output
    assert '"phase":"research_agent"' in output
    assert 'llm_call.started {"attempt":1,"phase":"finalizer"' in output
    assert '"phase":"finalizer"' in output


@pytest.mark.asyncio
async def test_graph_logs_model_failure_without_exception_message(caplog) -> None:
    secret = "AIza-should-not-be-logged"
    model = FakeChatModel(
        agent_outputs=cast(Sequence[AIMessage], [RuntimeError(secret)]),
        finalizer_outputs=[],
    )
    graph, _search, _pages = build_graph(model)

    with (
        caplog.at_level(logging.INFO, logger=LOGGER_NAME),
        pytest.raises(RuntimeError, match="should-not-be-logged"),
    ):
        await graph.ainvoke()

    output = "\n".join(record.getMessage() for record in caplog.records)
    assert "llm_call.started" in output
    assert "llm_call.failed" in output
    assert '"error_type":"RuntimeError"' in output
    assert secret not in output


@pytest.mark.asyncio
async def test_preloaded_pages_reach_models_and_count_toward_page_budget() -> None:
    registry = CandidateSourceRegistry()
    sources = [registry.register_hit(SearchHit(
        title=f"Research {i}", url=f"https://alice.example.edu/research-{i}",
    )) for i in range(6)]
    pages = FakePageExtractor(registry)
    initial = [await pages.extract(source.source_id, identity()) for source in sources[:2]]
    pages.source_ids.clear()
    model = FakeChatModel(
        agent_outputs=[
            tool_call("extract_candidate_page", {"source_id": "source_001"}, "repeat"),
            tool_call("extract_candidate_page", {"source_id": "source_003"}, "failed-repeat"),
            tool_call("extract_candidate_page", {"source_id": "source_004"}, "four"),
            tool_call("extract_candidate_page", {"source_id": "source_005"}, "five"),
            tool_call("extract_candidate_page", {"source_id": "source_006"}, "six"),
            AIMessage(content="Finalize"),
        ],
        finalizer_outputs=[final_result(evidence_source_id="source_001",
                                        homepage_source_id="source_001")],
    )
    graph = ProfessorResearchGraph(
        identity=identity(), chat_model=model, registry=registry,
        tools=create_research_tools(identity=identity(), registry=registry,
                                    tavily=FakeSearchProvider(), page_extractor=pages),
        initial_pages=initial, preloaded_sources=sources,
        attempted_source_ids=[source.source_id for source in sources[:3]],
    )
    result = await graph.ainvoke()
    assert result.publications == []
    assert pages.source_ids == ["source_004", "source_005"]
    payload = json.loads(str(model.finalizer_inputs[0][1].content))
    assert set(payload) == {"identity", "verified_pages"}
    assert [p["source_id"] for p in payload["verified_pages"]] == [
        "source_001", "source_002", "source_004", "source_005",
    ]
    first_input = str(model.agent_inputs[0][1].content)
    assert initial[0].text in first_input
    assert "source_002" in first_input
    messages = [m for invocation in model.agent_inputs for m in invocation]
    assert any("SOURCE_ALREADY_REQUESTED" in str(m.content) for m in messages)
    assert any("TOOL_BUDGET_EXCEEDED" in str(m.content) for m in messages)


def test_finalizer_schema_cannot_select_publications() -> None:
    assert "publication_source_ids" not in ProfessorResearchResult.model_json_schema()["properties"]
