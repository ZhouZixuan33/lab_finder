import asyncio
import json

import pytest
from langchain_core.messages import AIMessage

from lab_tracker.models.homepage import ReadWebpageResult
from lab_tracker.models.research import ResearchIdentity, SearchHit
from lab_tracker.services.research_graph import ResearchGraphError
from lab_tracker.services.unified_research_graph import UnifiedResearchGraph

OFFICIAL = "https://ece.illinois.edu/faculty/alice"
PERSONAL = "https://alice.example.org/"
PROJECT = "https://alice.example.org/projects"
IDENTITY = ResearchIdentity(
    name="Alice", title="Professor", affiliation="UIUC", official_profile_url=OFFICIAL
)
SUCCESS = {
    "status": "success",
    "research_summary": "Alice studies secure and reliable computer systems.",
    "tags": ["Security & Privacy"],
    "evidence_urls": ["https://not-read.example.org/"],
    "prospective_students_quote": "An unmatched quote is deliberately not validated.",
    "prospective_students_source_url": "https://not-read.example.org/",
}


def call(name, **args):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": args,
                "id": "call",
                "type": "tool_call",
            }
        ],
    )


class Script:
    def __init__(self, responses):
        self.responses = list(responses)
        self.inputs = []

    async def ainvoke(self, messages):
        self.inputs.append(messages)
        if not self.responses:
            raise AssertionError("Unexpected model call")
        response = self.responses.pop(0)
        if callable(response):
            return await response()
        return response


class Model:
    def __init__(self, home, research, final=(SUCCESS,)):
        self.home = Script(home)
        self.research = Script(research)
        self.final = Script(final)

    def bind_tools(self, tools, **kwargs):
        assert kwargs == {"parallel_tool_calls": False}
        names = {t.name for t in tools}
        if names == {"search_web", "read_webpage"}:
            return self.home
        assert names == {"read_webpage", "map_website"}
        return self.research

    def with_structured_output(self, schema, **kwargs):
        assert schema["name"] == "web_research_outcome"
        return self.final


class Web:
    def __init__(self):
        self.calls = []

    async def extract(self, url):
        self.calls.append(("read", url))
        return ReadWebpageResult(requested_url=url, url=url, content="Alice " + "x" * 14000)

    async def search(self, query):
        self.calls.append(("search", query))
        return [SearchHit(url=PERSONAL, title="Alice")]

    async def map(self, url, instructions):
        self.calls.append(("map", url))
        return [PROJECT]


def home():
    return [
        call("read_webpage", url=OFFICIAL),
        call("read_webpage", url=PERSONAL),
        AIMessage(content=json.dumps({"personal_homepage_url": PERSONAL})),
    ]


def graph(model, web, **kwargs):
    return UnifiedResearchGraph(
        identity=IDENTITY, chat_model=model, search=web, reader=web, mapper=web, **kwargs
    )


@pytest.mark.asyncio
async def test_shared_budget_without_shared_content_and_no_citation_audit():
    web = Web()
    model = Model(
        home(),
        [
            call("read_webpage", url=PERSONAL),
            call("map_website", url=PERSONAL, instructions="Find projects"),
            call("read_webpage", url=PROJECT),
            AIMessage(content="Done"),
        ],
    )
    instance = graph(model, web)
    result = await instance.ainvoke()
    assert [c for c in web.calls if c == ("read", PERSONAL)] == [("read", PERSONAL)] * 2
    assert len(model.research.inputs[0]) == 2
    assert "x" * 100 not in str(model.research.inputs[0])
    payload = json.loads(model.final.inputs[0][1].content)
    assert [p["url"] for p in payload["pages"]] == [PERSONAL, PROJECT]
    assert all(len(p["content"]) == 12000 and p["content_truncated"] for p in payload["pages"])
    assert result.source_urls == SUCCESS["evidence_urls"]
    assert result.prospective_students_quote == SUCCESS["prospective_students_quote"]
    assert result.personal_homepage_url == PERSONAL
    assert instance.latest == {}


@pytest.mark.asyncio
async def test_tenth_response_is_available_to_finalizer_no_eleventh_call():
    web = Web()
    research = [call("read_webpage", url=f"https://alice.example.org/{i}") for i in range(8)]
    model = Model(home(), research)
    await graph(model, web).ainvoke()
    assert len(web.calls) == 10
    assert len(model.research.inputs) == 8
    assert len(json.loads(model.final.inputs[0][1].content)["pages"]) == 8


@pytest.mark.asyncio
async def test_homepage_exhaustion_has_no_research_evidence():
    web = Web()
    model = Model([call("search_web", query="Alice") for _ in range(10)], [])
    with pytest.raises(ResearchGraphError, match="No research"):
        await graph(model, web).ainvoke()
    assert len(web.calls) == 10
    assert not model.research.inputs and not model.final.inputs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "final, attempts, fails",
    [
        ([{"status": "insufficient_evidence", "reason": "Only contact information"}], 1, True),
        ([{**SUCCESS, "tags": ["bad"]}, SUCCESS], 2, False),
        ([{**SUCCESS, "tags": ["bad"]}] * 2, 2, True),
    ],
)
async def test_finalizer_branches_and_one_correction(final, attempts, fails):
    model = Model(home(), [call("read_webpage", url=OFFICIAL), AIMessage(content="Done")], final)
    instance = graph(model, Web())
    if fails:
        with pytest.raises(ResearchGraphError):
            await instance.ainvoke()
    else:
        await instance.ainvoke()
    assert len(model.final.inputs) == attempts
    assert len(model.research.inputs) == 2


@pytest.mark.asyncio
async def test_invalid_research_search_is_rejected_without_network():
    web = Web()
    model = Model(
        home(),
        [
            call("search_web", query="elsewhere"),
            call("read_webpage", url=OFFICIAL),
            AIMessage(content="Done"),
        ],
    )
    await graph(model, web).ainvoke()
    assert all(kind == "read" for kind, _ in web.calls)
    assert model.research.inputs[1][-1].status == "error"


@pytest.mark.asyncio
async def test_collection_timeout_cancels_wait_and_finalizes_completed_evidence():
    cancelled = []

    async def slow():
        try:
            await asyncio.sleep(2)
        finally:
            cancelled.append(True)

    model = Model(home(), [call("read_webpage", url=OFFICIAL), slow])
    instance = graph(model, Web(), collection_seconds=0.15)
    result = await instance.ainvoke()
    assert cancelled and result.tags == SUCCESS["tags"]
    assert len(model.final.inputs) == 1
    assert instance.latest == {}


@pytest.mark.asyncio
async def test_finalizer_timeout_is_not_retried():
    async def slow():
        await asyncio.sleep(2)

    model = Model(home(), [call("read_webpage", url=OFFICIAL), AIMessage(content="Done")], [slow])
    with pytest.raises(ResearchGraphError, match="Finalizer"):
        await graph(model, Web(), finalizer_seconds=0.01).ainvoke()
    assert len(model.final.inputs) == 1


@pytest.mark.asyncio
async def test_step_limit_ends_invalid_call_loop():
    model = Model([call("missing", url=OFFICIAL)] * 20, [])
    web = Web()
    with pytest.raises(ResearchGraphError, match="No research"):
        await graph(model, web, recursion_limit=6).ainvoke()
    assert not web.calls


@pytest.mark.asyncio
async def test_external_cancellation_is_not_converted_to_success():
    started = asyncio.Event()

    async def wait():
        started.set()
        await asyncio.sleep(10)

    model = Model(home(), [wait])
    instance = graph(model, Web())
    task = asyncio.create_task(instance.ainvoke())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not model.final.inputs and instance.latest == {}


@pytest.mark.asyncio
async def test_failed_requests_count_and_no_search_in_research():
    class FailingWeb(Web):
        async def extract(self, url):
            self.calls.append(("read", url))
            raise ValueError("Extraction failed")

    web = FailingWeb()
    model = Model(
        [AIMessage(content='{"personal_homepage_url": null}')],
        [call("read_webpage", url=OFFICIAL)] * 10,
    )
    with pytest.raises(ResearchGraphError, match="No research"):
        await graph(model, web).ainvoke()
    assert len(web.calls) == 10 and not model.final.inputs


@pytest.mark.asyncio
async def test_actual_chat_adapter_uses_tool_calling_for_both_outcome_branches():
    import httpx
    from langchain_openai import ChatOpenAI

    final_requests = []
    turn = 0

    def handle(request):
        nonlocal turn
        payload = json.loads(request.content)
        turn += 1
        if turn == 1:
            message = {"role": "assistant", "content": '{"personal_homepage_url": null}'}
        elif turn == 2:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "read-1",
                        "type": "function",
                        "function": {
                            "name": "read_webpage",
                            "arguments": json.dumps({"url": OFFICIAL}),
                        },
                    }
                ],
            }
        elif turn == 3:
            message = {"role": "assistant", "content": "Done"}
        else:
            final_requests.append(payload)
            assert "response_format" not in payload
            function = payload["tools"][0]["function"]
            assert function["name"] == "web_research_outcome"
            assert function["strict"] is False
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "result",
                        "type": "function",
                        "function": {
                            "name": "web_research_outcome",
                            "arguments": json.dumps(SUCCESS),
                        },
                    }
                ],
            }
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        model = ChatOpenAI(
            model="test",
            api_key="fake",
            base_url="https://mock.example/v1",
            http_async_client=client,
            max_retries=0,
        )
        result = await graph(model, Web()).ainvoke()
    assert result.tags == SUCCESS["tags"] and len(final_requests) == 1
