"""LangChain tools with minimal model-visible argument schemas."""

from typing import Protocol

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

from lab_tracker.models.common import DomainModel
from lab_tracker.models.research import (
    ExtractedPage,
    ResearchIdentity,
    SearchHit,
)
from lab_tracker.services.research_sources import CandidateSourceRegistry


class SearchProvider(Protocol):
    async def search(self, query: str) -> list[SearchHit]: ...


class ExtractProvider(Protocol):
    async def extract(self, source_id: str, identity: ResearchIdentity) -> ExtractedPage: ...


class SearchProfessorWebInput(DomainModel):
    query: str = Field(min_length=1, max_length=500)


class ExtractCandidatePageInput(DomainModel):
    source_id: str = Field(pattern=r"^source_[0-9]{3}$")


def create_research_tools(
    *,
    identity: ResearchIdentity,
    registry: CandidateSourceRegistry,
    tavily: SearchProvider,
    page_extractor: ExtractProvider,
) -> list[BaseTool]:
    async def search_professor_web(query: str) -> list[dict[str, object]]:
        hits = await tavily.search(query)
        return [
            source.model_dump(mode="json")
            for source in registry.register_hits(hits)
        ]

    async def extract_candidate_page(source_id: str) -> dict[str, object]:
        page = await page_extractor.extract(source_id, identity)
        return page.model_dump(mode="json")

    return [
        StructuredTool.from_function(
            coroutine=search_professor_web,
            name="search_professor_web",
            description=(
                "Search for the named professor's official profile "
                "and research evidence. Input only a focused search query."
            ),
            args_schema=SearchProfessorWebInput,
        ),
        StructuredTool.from_function(
            coroutine=extract_candidate_page,
            name="extract_candidate_page",
            description=(
                "Extract sanitized text from one registered search result. "
                "Input only a source_id returned by search_professor_web."
            ),
            args_schema=ExtractCandidatePageInput,
        ),
    ]
