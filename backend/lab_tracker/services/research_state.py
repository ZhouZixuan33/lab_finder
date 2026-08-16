"""Typed LangGraph state for one professor research run."""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from lab_tracker.models.research import (
    ExtractedPage,
    OpenAlexPublication,
    ResearchIdentity,
    ValidatedProfessorResearch,
)


class ResearchState(TypedDict, total=False):
    identity: ResearchIdentity
    messages: Annotated[list[BaseMessage], add_messages]
    turn_count: int
    search_calls: int
    page_source_ids_attempted: list[str]
    openalex_calls: int
    pages: list[ExtractedPage]
    publications: list[OpenAlexPublication]
    recorded_tool_call_ids: list[str]
    guard_allowed: bool
    force_finalize: bool
    finalizer_errors: list[str]
    final_result: ValidatedProfessorResearch
    failure_message: str
