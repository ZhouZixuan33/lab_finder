"""The two tools visible to the homepage agent."""

from typing import Protocol

from langchain_core.tools import BaseTool, StructuredTool

from lab_tracker.models.homepage import ReadWebpageInput, ReadWebpageResult, SearchWebInput
from lab_tracker.services.research_tools import SearchProvider

SEARCH_DESCRIPTION = (
    "A web search tool powered by the Tavily Search API. Provide an appropriate query "
    "using the professor's name, affiliation, and terms such as personal homepage or "
    "personal website. Tavily searches the web and returns candidate links to the "
    "professor's personal homepage, along with page titles and snippets. Results are "
    "candidates, not verified homepages. Use read_webpage to inspect promising links "
    "and confirm the professor's identity before selecting a final URL."
)
READ_DESCRIPTION = (
    "Read one public webpage using Tavily Extract. Returns extracted Markdown, which "
    "may contain page links. Use it to inspect an official faculty profile or verify "
    "a candidate personal homepage. Extraction may omit some content or links; an "
    "extraction failure is not evidence that a homepage does not exist."
)


class WebpageProvider(Protocol):
    async def extract(self, url: str) -> ReadWebpageResult: ...


def create_homepage_tools(*, search: SearchProvider, reader: WebpageProvider) -> list[BaseTool]:
    async def search_web(query: str) -> dict[str, object]:
        hits = await search.search(query)
        return {
            "results": [
                {"title": hit.title, "url": hit.url, "snippet": hit.snippet[:1_200]}
                for hit in hits[:5]
            ]
        }

    async def read_webpage(url: str) -> dict[str, object]:
        return (await reader.extract(url)).model_dump(mode="json")

    return [
        StructuredTool.from_function(
            coroutine=search_web,
            name="search_web",
            description=SEARCH_DESCRIPTION,
            args_schema=SearchWebInput,
        ),
        StructuredTool.from_function(
            coroutine=read_webpage,
            name="read_webpage",
            description=READ_DESCRIPTION,
            args_schema=ReadWebpageInput,
        ),
    ]
