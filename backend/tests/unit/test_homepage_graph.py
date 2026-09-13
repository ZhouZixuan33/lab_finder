import json
from collections import deque

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from lab_tracker.models.homepage import ReadWebpageResult
from lab_tracker.models.research import ResearchIdentity, SearchHit
from lab_tracker.services.homepage_graph import HomepageGraph
from lab_tracker.services.homepage_tools import create_homepage_tools

OFFICIAL = "https://ece.illinois.edu/about/directory/faculty/alice"
PERSONAL = "https://alice.github.io/"


def identity():
    return ResearchIdentity(
        name="Alice Systems",
        title="Professor",
        affiliation="UIUC",
        official_profile_url=OFFICIAL,
    )


def call(name, args, number):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": str(number)}])


class FakeRunnable:
    def __init__(self, outputs):
        self.outputs = deque(outputs)
        self.inputs = []

    async def ainvoke(self, value):
        self.inputs.append(value)
        output = self.outputs.popleft()
        if isinstance(output, Exception):
            raise output
        return output


class FakeModel:
    def __init__(self, outputs, final):
        self.agent = FakeRunnable(outputs)
        self.finalizer = FakeRunnable([final])

    def bind_tools(self, tools, **kwargs):
        self.tools = tools
        assert kwargs["parallel_tool_calls"] is False
        return self.agent

    def with_structured_output(self, schema):
        self.schema = schema
        return self.finalizer


class FakeWeb:
    def __init__(self, *, fail=False):
        self.urls = []
        self.queries = []
        self.fail = fail

    async def search(self, query):
        self.queries.append(query)
        return [SearchHit(title="Alice Systems", url=PERSONAL, snippet="UIUC personal website")]

    async def extract(self, url):
        self.urls.append(url)
        if self.fail:
            raise RuntimeError("secret-provider-key must not be shown")
        return ReadWebpageResult(
            requested_url=url,
            url=url,
            content=f"Alice Systems at UIUC. [Personal Website]({PERSONAL})",
        )


def graph(model, web):
    return HomepageGraph(
        identity=identity(),
        chat_model=model,
        tools=create_homepage_tools(search=web, reader=web),
    )


@pytest.mark.asyncio
async def test_official_link_example_has_four_model_calls_and_accumulated_messages():
    model = FakeModel(
        [
            call("read_webpage", {"url": OFFICIAL}, 1),
            call("read_webpage", {"url": PERSONAL}, 2),
            AIMessage(content="Confirmed"),
        ],
        {"personal_homepage_url": PERSONAL},
    )
    web = FakeWeb()
    assert await graph(model, web).ainvoke() == PERSONAL
    assert web.urls == [OFFICIAL, PERSONAL]
    assert web.queries == []
    assert [len(messages) for messages in model.agent.inputs] == [2, 4, 6]
    history = model.agent.inputs[-1]
    assert [type(message) for message in history] == [
        SystemMessage,
        HumanMessage,
        AIMessage,
        ToolMessage,
        AIMessage,
        ToolMessage,
    ]
    assert history[3].tool_call_id == "1"
    assert history[5].tool_call_id == "2"
    assert len(model.finalizer.inputs) == 1
    assert all(isinstance(m, (SystemMessage, HumanMessage)) for m in model.finalizer.inputs[0])
    assert "先读取官方介绍页" in history[0].content


@pytest.mark.asyncio
async def test_fifth_tool_result_goes_directly_to_finalizer():
    model = FakeModel(
        [call("search_web", {"query": f"Alice homepage {i}"}, i) for i in range(4)]
        + [call("read_webpage", {"url": PERSONAL}, 5)],
        {"personal_homepage_url": PERSONAL},
    )
    web = FakeWeb()
    assert await graph(model, web).ainvoke() == PERSONAL
    assert len(model.agent.inputs) == 5
    assert len(model.finalizer.inputs) == 1
    assert PERSONAL in model.finalizer.inputs[0][1].content


@pytest.mark.asyncio
async def test_failed_reads_consume_budget_and_do_not_leak_errors():
    model = FakeModel(
        [call("read_webpage", {"url": PERSONAL}, i) for i in range(5)],
        {"personal_homepage_url": PERSONAL},
    )
    web = FakeWeb(fail=True)
    assert await graph(model, web).ainvoke() is None
    assert len(web.urls) == 5
    tool_message = model.agent.inputs[1][-1]
    assert tool_message.status == "error"
    assert "secret-provider-key" not in tool_message.content
    assert json.loads(tool_message.content)["error"]["code"] == "TOOL_EXECUTION_FAILED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "final",
    [
        {"personal_homepage_url": "https://unread.example.org"},
        {"personal_homepage_url": OFFICIAL},
        {"personal_homepage_url": None},
        {"personal_homepage_url": 42},
        {"wrong_field": PERSONAL},
    ],
)
async def test_invalid_unread_or_official_result_is_null(final):
    model = FakeModel(
        [
            call("read_webpage", {"url": OFFICIAL}, 1),
            AIMessage(content="Done"),
        ],
        final,
    )
    assert await graph(model, FakeWeb()).ainvoke() is None


@pytest.mark.asyncio
async def test_parallel_request_is_not_executed_or_replayed_to_finalizer():
    message = AIMessage(
        content="",
        tool_calls=[
            {"name": "read_webpage", "args": {"url": OFFICIAL}, "id": "1"},
            {"name": "read_webpage", "args": {"url": PERSONAL}, "id": "2"},
        ],
    )
    model = FakeModel([message], {"personal_homepage_url": None})
    web = FakeWeb()
    assert await graph(model, web).ainvoke() is None
    assert web.urls == []
    assert len(model.agent.inputs) == 1
    assert all(isinstance(m, (SystemMessage, HumanMessage)) for m in model.finalizer.inputs[0])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,args",
    [
        ("unknown", {}),
        ("read_webpage", {"url": "http://localhost"}),
        ("search_web", {"query": "Alice", "api_key": "secret-provider-key"}),
    ],
)
async def test_bad_arguments_and_unknown_tools_are_bounded(name, args):
    model = FakeModel([call(name, args, i) for i in range(5)], {"personal_homepage_url": None})
    web = FakeWeb()
    assert await graph(model, web).ainvoke() is None
    assert len(model.agent.inputs) == 5
    assert web.urls == web.queries == []
    assert "secret-provider-key" not in model.agent.inputs[1][-1].content


@pytest.mark.asyncio
async def test_model_api_failure_propagates():
    model = FakeModel([AIMessage(content="Done")], ValueError("Model unavailable"))
    with pytest.raises(ValueError, match="Model unavailable"):
        await graph(model, FakeWeb()).ainvoke()


@pytest.mark.asyncio
async def test_search_then_read_is_supported_without_source_ids():
    model = FakeModel(
        [
            call("search_web", {"query": "Alice UIUC homepage"}, 1),
            call("read_webpage", {"url": PERSONAL}, 2),
            AIMessage(content="Done"),
        ],
        {"personal_homepage_url": PERSONAL},
    )
    web = FakeWeb()
    assert await graph(model, web).ainvoke() == PERSONAL
    result = json.loads(model.agent.inputs[1][-1].content)
    assert result["results"][0]["url"] == PERSONAL
    assert "source_id" not in result["results"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("refresh", [False, True])
@pytest.mark.parametrize("author_missing", [False, True])
async def test_researcher_maps_homepage_to_lab_url_and_preserves_research(
    monkeypatch, refresh, author_missing,
):
    from lab_tracker.models.research import ValidatedProfessorResearch
    from lab_tracker.services import update_checks
    from lab_tracker.services.discovery import FacultyCandidate
    from lab_tracker.services.openalex_provider import OpenAlexAuthorNotFoundError

    research = ValidatedProfessorResearch(
        research_summary="Existing summary",
        tags=["Security & Privacy"],
        homepage_url=OFFICIAL,
        source_urls=[OFFICIAL],
    )

    class FakeResearchGraph:
        def __init__(self, **kwargs):
            assert web.urls == [PERSONAL]  # Homepage discovery already ran.
            assert http.urls == [OFFICIAL, PERSONAL.rstrip("/")]
            assert [page.url for page in kwargs["initial_pages"]] == [
                OFFICIAL, PERSONAL.rstrip("/"),
            ]
            assert kwargs["attempted_source_ids"] == ["source_001", "source_002"]
            assert "get_recent_publications" not in [tool.name for tool in kwargs["tools"]]
            assert publications.calls == 0

        async def ainvoke(self):
            events.append("summary_validated")
            return research

    class FakePublications:
        calls = 0

        async def get_recent_publications(self, identity):
            assert events == ["summary_validated"]
            events.append("publications")
            self.calls += 1
            if author_missing:
                raise OpenAlexAuthorNotFoundError("No matching author")
            return []

    class FakeHttp:
        def __init__(self):
            self.urls = []

        async def get(self, url):
            self.urls.append(url)
            return httpx.Response(200, request=httpx.Request("GET", url), text=(
                "<main>Alice Systems at UIUC researches secure computing systems.</main>"
            ))

    monkeypatch.setattr(update_checks, "ProfessorResearchGraph", FakeResearchGraph)
    web = FakeWeb()
    model = FakeModel(
        [
            call("read_webpage", {"url": PERSONAL}, 1),
            AIMessage(content="Done"),
        ],
        {"personal_homepage_url": PERSONAL},
    )
    publications = FakePublications()
    events = []
    http = FakeHttp()
    researcher = update_checks.LangGraphCandidateResearcher(
        chat_model=model,
        tavily=web,
        openalex=publications,
        page_http=http,
        homepage_reader=web,
    )
    candidate = FacultyCandidate(
        name="Alice Systems",
        title="Professor",
        email=None,
        directory_profile_url=OFFICIAL,
    )
    result = await (
        researcher.research_with_refresh(candidate) if refresh else researcher.research(candidate)
    )
    assert result.lab_url == PERSONAL
    assert result.homepage_url == research.homepage_url
    assert result.research_summary == research.research_summary
    assert result.publications == research.publications
    assert result.tags == research.tags
    assert result.source_urls == research.source_urls
    assert research.lab_url is None  # Do not mutate the old graph's result.
    assert result.publications_unavailable is author_missing
    assert publications.calls == 1
    assert events == ["summary_validated", "publications"]


@pytest.mark.asyncio
async def test_publication_lookup_does_not_hide_other_errors():
    from lab_tracker.services.openalex_provider import AmbiguousOpenAlexAuthorError
    from lab_tracker.services.update_checks import _PublicationLookup

    class BrokenProvider:
        async def get_recent_publications(self, identity):
            raise AmbiguousOpenAlexAuthorError("Multiple matches")

    with pytest.raises(AmbiguousOpenAlexAuthorError):
        await _PublicationLookup(BrokenProvider()).get_recent_publications(identity())
