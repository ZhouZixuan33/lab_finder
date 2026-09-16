import json
from contextlib import asynccontextmanager

import httpx
import pytest
from pydantic import SecretStr

from lab_tracker.models.homepage import validate_public_url
from lab_tracker.services.tavily_extract import TavilyExtractProvider


class FakeLimiter:
    def __init__(self):
        self.calls = 0

    @asynccontextmanager
    async def slot(self):
        self.calls += 1
        yield


@pytest.mark.asyncio
async def test_extract_single_url_request_and_markdown_truncation():
    url = "https://alice.github.io/"
    markdown = "[Personal website](https://alice.github.io/)\n" + "x" * 12_000

    def handle(request):
        assert str(request.url) == "https://api.tavily.com/extract"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert json.loads(request.content) == {
            "urls": [url],
            "extract_depth": "advanced",
            "format": "markdown",
            "include_images": False,
            "include_favicon": False,
            "timeout": 10,
        }
        assert request.extensions["timeout"]["read"] == 20
        return httpx.Response(
            200,
            json={
                "results": [{"url": url, "raw_content": markdown}],
                "failed_results": [],
            },
        )

    limiter = FakeLimiter()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = TavilyExtractProvider(client, api_key=SecretStr("test-key"), limiter=limiter)
        result = await provider.extract(url)
    assert result.requested_url == result.url == url
    assert result.content == markdown[:12_000]
    assert result.content_truncated is True
    assert result.original_content_chars == len(markdown)
    assert result.truncated is False
    assert limiter.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"results": [], "failed_results": [{"url": "https://alice.github.io", "error": "Failed"}]},
        {"results": [{"url": "https://alice.github.io", "raw_content": "   "}]},
        {"results": [{"url": "https://alice.github.io", "raw_content": None}]},
    ],
)
async def test_failed_or_empty_extraction_is_not_success(payload):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    ) as client:
        provider = TavilyExtractProvider(
            client,
            api_key=SecretStr("key"),
            limiter=FakeLimiter(),
        )
        with pytest.raises(ValueError, match="No readable content"):
            await provider.extract("https://alice.github.io")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "timeout"])
async def test_extract_does_not_retry_provider_failures(failure):
    attempts = []

    def handle(request):
        attempts.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(429)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = TavilyExtractProvider(
            client,
            api_key=SecretStr("key"),
            limiter=FakeLimiter(),
        )
        with pytest.raises(httpx.HTTPError):
            await provider.extract("https://alice.github.io")
    assert len(attempts) == 1


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost",
        "http://localhost./",
        "http://127.0.0.1",
        "http://[::1]",
        "https://10.0.0.1",
        "https://user:password@example.org",
        "http://2130706433",
        "http://127.1",
        "http://host.local",
        "https://example.org:wrong",
    ],
)
def test_reject_non_public_inputs(url):
    with pytest.raises(ValueError):
        validate_public_url(url)
