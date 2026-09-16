import json
from contextlib import asynccontextmanager

import httpx
import pytest
from pydantic import SecretStr

from lab_tracker.services.tavily_extract import TavilyExtractProvider
from lab_tracker.services.tavily_provider import TavilyProvider


class Limiter:
    @asynccontextmanager
    async def slot(self):
        yield


@pytest.mark.asyncio
async def test_map_has_one_bounded_request_and_returns_urls():
    calls = []

    def handle(request):
        calls.append(request)
        payload = json.loads(request.content)
        assert payload["limit"] == 20 and payload["max_depth"] == 2
        assert payload["instructions"] == "Find research"
        assert str(request.url) == "https://api.tavily.com/map"
        return httpx.Response(200, json={"results": [f"https://site.edu/{i}" for i in range(30)]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = TavilyExtractProvider(client, api_key=SecretStr("fake"), limiter=Limiter())
        results = await provider.map("https://site.edu", "Find research")
    assert len(calls) == 1 and len(results) == 20


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 429])
async def test_direct_search_has_no_hidden_retries(status):
    calls = []

    def handle(request):
        calls.append(request)
        assert str(request.url) == "https://api.tavily.com/search"
        assert json.loads(request.content)["query"] == "Alice homepage"
        return httpx.Response(
            status,
            json={
                "results": [
                    {"title": "Alice", "url": "https://alice.edu", "content": "profile"},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = TavilyProvider(client=client, api_key=SecretStr("fake"), limiter=Limiter())
        if status == 200:
            assert (await provider.search("Alice   homepage"))[0].url == "https://alice.edu"
        else:
            with pytest.raises(httpx.HTTPStatusError):
                await provider.search("Alice homepage")
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [11999, 12000, 12001])
async def test_read_truncation_boundary(size):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"results": [{"url": "https://alice.edu", "raw_content": "a" * size}]},
            )
        )
    ) as client:
        provider = TavilyExtractProvider(client, api_key=SecretStr("fake"), limiter=Limiter())
        page = await provider.extract("https://alice.edu")
    assert len(page.content) == min(size, 12000)
    assert page.content_truncated == (size > 12000)
    assert page.original_content_chars == size
