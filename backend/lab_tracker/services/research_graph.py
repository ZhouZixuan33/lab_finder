"""Explicit bounded LangGraph workflow for one professor research run."""

import json
from collections.abc import Sequence
from typing import Any, Literal, Protocol, cast

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import ValidationError

from lab_tracker.models.research import (
    ExtractedPage,
    OpenAlexPublication,
    ProfessorResearchResult,
    RegisteredSource,
    ResearchIdentity,
    SearchHit,
    ValidatedProfessorResearch,
)
from lab_tracker.services.research_prompts import (
    build_agent_messages,
    build_finalizer_messages,
)
from lab_tracker.services.research_sources import (
    CandidateSourceRegistry,
    UnknownSourceError,
)
from lab_tracker.services.research_state import ResearchState
from lab_tracker.services.research_validation import (
    ResearchValidationError,
    validate_research_result,
)

MAX_AGENT_TURNS = 8
MAX_SEARCH_CALLS = 3
MAX_PAGE_CALLS = 5
MAX_OPENALEX_CALLS = 1
GRAPH_RECURSION_LIMIT = 24

TOOL_ARGUMENTS = {
    "search_professor_web": frozenset({"query"}),
    "extract_candidate_page": frozenset({"source_id"}),
    "get_recent_publications": frozenset(),
}


class AsyncRunnable(Protocol):
    async def ainvoke(self, value: Any) -> Any: ...


class ResearchChatModel(Protocol):
    def bind_tools(self, tools: Sequence[BaseTool], **kwargs: object) -> AsyncRunnable: ...

    def with_structured_output(self, schema: object) -> AsyncRunnable: ...


class ResearchGraphError(RuntimeError):
    pass


class ProfessorResearchGraph:
    def __init__(
        self,
        *,
        identity: ResearchIdentity,
        chat_model: ResearchChatModel,
        tools: Sequence[BaseTool],
        registry: CandidateSourceRegistry,
        initial_publications: Sequence[OpenAlexPublication] = (),
        preloaded_sources: Sequence[RegisteredSource] = (),
    ) -> None:
        self.identity = identity
        self.registry = registry
        self.tools = list(tools)
        self.initial_publications = list(initial_publications)
        self.preloaded_sources = list(preloaded_sources)
        self.official_source = registry.register_hit(
            SearchHit(
                title=f"Official UIUC profile for {identity.name}",
                url=identity.official_profile_url,
                snippet="Official UIUC ECE faculty profile.",
            )
        )
        self.agent_model = chat_model.bind_tools(
            self.tools,
            parallel_tool_calls=False,
        )
        self.finalizer_model = chat_model.with_structured_output(ProfessorResearchResult)
        self.graph = self._build_graph()

    def _build_graph(self):  # type: ignore[no-untyped-def]
        builder = StateGraph(ResearchState)
        builder.add_node("research_agent", self._agent_node)
        builder.add_node("tool_budget_guard", self._guard_node)
        builder.add_node(
            "tools",
            ToolNode(
                self.tools,
                handle_tool_errors=lambda error: json.dumps(
                    {"error": {"code": "TOOL_EXECUTION_FAILED", "message": str(error)}}
                ),
            ),
        )
        builder.add_node("finalizer", self._finalizer_node)
        builder.add_edge(START, "research_agent")
        builder.add_conditional_edges(
            "research_agent",
            self._route_agent,
            {"guard": "tool_budget_guard", "finalize": "finalizer"},
        )
        builder.add_conditional_edges(
            "tool_budget_guard",
            self._route_guard,
            {"tools": "tools", "agent": "research_agent", "finalize": "finalizer"},
        )
        builder.add_edge("tools", "research_agent")
        builder.add_edge("finalizer", END)
        return builder.compile(name="professor_research_graph")

    async def ainvoke(self) -> ValidatedProfessorResearch:
        initial_state: ResearchState = {
            "identity": self.identity,
            "messages": build_agent_messages(
                self.identity,
                official_source_id=self.official_source.source_id,
                preloaded_sources=self.preloaded_sources,
            ),
            "turn_count": 0,
            "search_calls": 0,
            "page_source_ids_attempted": [],
            "openalex_calls": 0,
            "pages": [],
            "publications": list(self.initial_publications),
            "recorded_tool_call_ids": [],
            "guard_allowed": False,
            "force_finalize": False,
            "finalizer_errors": [],
        }
        final_state = await self.graph.ainvoke(
            initial_state,
            config={"recursion_limit": GRAPH_RECURSION_LIMIT},
        )
        if failure_message := final_state.get("failure_message"):
            raise ResearchGraphError(failure_message)
        result = final_state.get("final_result")
        if result is None:
            raise ResearchGraphError("Research graph ended without a validated result")
        return result

    async def _agent_node(self, state: ResearchState) -> ResearchState:
        updates = self._record_last_tool_output(state)
        if state.get("turn_count", 0) >= MAX_AGENT_TURNS:
            return {**updates, "force_finalize": True}

        response = await self.agent_model.ainvoke(state["messages"])
        if not isinstance(response, AIMessage):
            raise ResearchGraphError("Research agent returned a non-AI message")
        return {
            **updates,
            "messages": [response],
            "turn_count": state.get("turn_count", 0) + 1,
            "force_finalize": False,
        }

    def _record_last_tool_output(self, state: ResearchState) -> ResearchState:
        messages = state.get("messages", [])
        if not messages or not isinstance(messages[-1], ToolMessage):
            return {}
        message = messages[-1]
        recorded = list(state.get("recorded_tool_call_ids", []))
        if message.tool_call_id in recorded:
            return {}
        recorded.append(message.tool_call_id)
        updates: ResearchState = {"recorded_tool_call_ids": recorded}

        if not isinstance(message.content, str):
            return updates
        try:
            payload = json.loads(message.content)
        except json.JSONDecodeError:
            return updates

        if message.name == "extract_candidate_page" and isinstance(payload, dict):
            try:
                page = ExtractedPage.model_validate(payload)
                registered = self.registry.get(page.source_id)
            except (ValidationError, UnknownSourceError):
                return updates
            if page.url == registered.url and page.candidate_id == registered.candidate_id:
                pages_by_id = {
                    page_item.source_id: page_item for page_item in state.get("pages", [])
                }
                pages_by_id[page.source_id] = page
                updates["pages"] = list(pages_by_id.values())
        elif message.name == "get_recent_publications" and isinstance(payload, list):
            publications: list[OpenAlexPublication] = []
            for item in payload:
                try:
                    publications.append(OpenAlexPublication.model_validate(item))
                except ValidationError:
                    continue
            updates["publications"] = publications
        return updates

    @staticmethod
    def _route_agent(state: ResearchState) -> Literal["guard", "finalize"]:
        if state.get("force_finalize"):
            return "finalize"
        messages = state.get("messages", [])
        if messages and isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
            return "guard"
        return "finalize"

    def _guard_node(self, state: ResearchState) -> ResearchState:
        message = cast(AIMessage, state["messages"][-1])
        calls = message.tool_calls
        if len(calls) != 1:
            return self._guard_error(
                calls,
                code="PARALLEL_TOOL_CALLS_NOT_ALLOWED",
                message="Exactly one tool call is allowed per model response.",
            )

        call = calls[0]
        name = call.get("name", "")
        arguments = call.get("args", {})
        if name not in TOOL_ARGUMENTS:
            return self._guard_error(
                calls,
                code="UNKNOWN_TOOL",
                message=f"Unknown research tool: {name}",
            )
        if not isinstance(arguments, dict) or set(arguments) != TOOL_ARGUMENTS[name]:
            return self._guard_error(
                calls,
                code="INVALID_TOOL_ARGUMENTS",
                message="Tool arguments attempted to add, omit, or override protected fields.",
            )

        updates: ResearchState = {"guard_allowed": True}
        if name == "search_professor_web":
            count = state.get("search_calls", 0)
            if count >= MAX_SEARCH_CALLS:
                return self._guard_error(
                    calls,
                    code="TOOL_BUDGET_EXCEEDED",
                    message="Tavily search budget is exhausted.",
                )
            updates["search_calls"] = count + 1
        elif name == "extract_candidate_page":
            source_id = arguments["source_id"]
            if not isinstance(source_id, str):
                return self._guard_error(
                    calls,
                    code="INVALID_SOURCE_ID",
                    message="source_id must be a registered source ID.",
                )
            try:
                self.registry.get(source_id)
            except UnknownSourceError:
                return self._guard_error(
                    calls,
                    code="UNKNOWN_SOURCE_ID",
                    message="The requested page was not registered by the server.",
                )
            attempted = list(state.get("page_source_ids_attempted", []))
            if source_id in attempted:
                return self._guard_error(
                    calls,
                    code="SOURCE_ALREADY_REQUESTED",
                    message="Each registered page can be opened only once.",
                )
            if len(attempted) >= MAX_PAGE_CALLS:
                return self._guard_error(
                    calls,
                    code="TOOL_BUDGET_EXCEEDED",
                    message="Unique page extraction budget is exhausted.",
                )
            updates["page_source_ids_attempted"] = [*attempted, source_id]
        else:
            count = state.get("openalex_calls", 0)
            if count >= MAX_OPENALEX_CALLS:
                return self._guard_error(
                    calls,
                    code="TOOL_BUDGET_EXCEEDED",
                    message="OpenAlex budget is exhausted.",
                )
            updates["openalex_calls"] = count + 1
        return updates

    @staticmethod
    def _guard_error(
        calls: list[dict[str, Any]],
        *,
        code: str,
        message: str,
    ) -> ResearchState:
        error_content = json.dumps({"error": {"code": code, "message": message}})
        tool_messages = [
            ToolMessage(
                content=error_content,
                tool_call_id=str(call.get("id", "unknown")),
                name=str(call.get("name", "unknown")),
            )
            for call in calls
        ]
        return {"guard_allowed": False, "messages": tool_messages}

    @staticmethod
    def _route_guard(state: ResearchState) -> Literal["tools", "agent", "finalize"]:
        if state.get("guard_allowed"):
            return "tools"
        if state.get("turn_count", 0) >= MAX_AGENT_TURNS:
            return "finalize"
        return "agent"

    async def _finalizer_node(self, state: ResearchState) -> ResearchState:
        errors = list(state.get("finalizer_errors", []))
        pages = state.get("pages", [])
        publications = state.get("publications", [])
        for _attempt in range(3):
            messages = build_finalizer_messages(
                self.identity,
                pages=pages,
                publications=publications,
                previous_errors=errors,
            )
            try:
                raw_result = await self.finalizer_model.ainvoke(messages)
                result = ProfessorResearchResult.model_validate(raw_result)
                validated = validate_research_result(
                    result,
                    pages=pages,
                    publications=publications,
                    registry=self.registry,
                )
            except (ValidationError, ResearchValidationError, ValueError) as error:
                errors.append(str(error))
                continue
            return {"final_result": validated, "finalizer_errors": errors}

        last_error = errors[-1] if errors else "unknown validation error"
        return {
            "failure_message": f"Research finalization failed: {last_error}",
            "finalizer_errors": errors,
        }
