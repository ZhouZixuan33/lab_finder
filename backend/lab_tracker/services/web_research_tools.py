"""URL tools shared by graph stages; budget enforcement belongs to the graph."""

from typing import Protocol

from langchain_core.tools import StructuredTool
from pydantic import Field

from lab_tracker.models.homepage import ReadWebpageInput, SearchWebInput
from lab_tracker.services.homepage_tools import WebpageProvider
from lab_tracker.services.research_tools import SearchProvider


class MapProvider(Protocol):
    async def map(self, url: str, instructions: str) -> list[str]: ...


class MapWebsiteInput(ReadWebpageInput):
    instructions: str = Field(min_length=1, max_length=500)


def create_web_tools(*, search: SearchProvider, reader: WebpageProvider, mapper: MapProvider):
    async def search_web(query: str):
        hits = await search.search(query)
        return {
            "results": [
                {"url": hit.url, "title": hit.title, "snippet": hit.snippet[:1200]}
                for hit in hits[:5]
            ]
        }

    async def read_webpage(url: str):
        page = await reader.extract(url)
        content = page.content
        return {
            **page.model_dump(mode="json"),
            "content": content[:12000],
            "content_truncated": page.content_truncated or len(content) > 12000,
            "original_content_chars": page.original_content_chars or len(content),
        }

    async def map_website(url: str, instructions: str):
        return {"url": url, "results": (await mapper.map(url, instructions))[:20]}

    specs = [
        (search_web, SearchWebInput, "Search for candidate personal homepages."),
        (
            read_webpage,
            ReadWebpageInput,
            "Read one public URL with Tavily Extract. Markdown may contain links. "
            "Content may be truncated; omitted information is not proof of absence.",
        ),
        (
            map_website,
            MapWebsiteInput,
            "Discover relevant page URLs within a website. Map does not read their content.",
        ),
    ]
    return {
        function.__name__: StructuredTool.from_function(
            coroutine=function,
            name=function.__name__,
            description=description,
            args_schema=schema,
        )
        for function, schema, description in specs
    }
