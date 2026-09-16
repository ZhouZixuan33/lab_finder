"""Thin asynchronous Tavily Extract adapter; no local HTML parsing."""

import httpx
from pydantic import SecretStr

from lab_tracker.models.homepage import ReadWebpageResult, validate_public_url
from lab_tracker.services.rate_limit import SerialRateLimiter

MAX_CONTENT_CHARACTERS = 12_000


class TavilyExtractProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: SecretStr,
        limiter: SerialRateLimiter,
    ) -> None:
        self.client = client
        self._api_key = api_key
        self.limiter = limiter

    async def extract(self, url: str) -> ReadWebpageResult:
        url = validate_public_url(url)
        async with self.limiter.slot():
            response = await self.client.post(
                "https://api.tavily.com/extract",
                headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
                json={
                    "urls": [url],
                    "extract_depth": "advanced",
                    "format": "markdown",
                    "include_images": False,
                    "include_favicon": False,
                    "timeout": 10,
                },
                timeout=20,
                follow_redirects=False,
            )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if len(results) != 1 or not isinstance(results[0], dict):
            raise ValueError("No readable content was returned for this URL")
        result = results[0]
        content = result.get("raw_content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("No readable content was returned for this URL")
        content = content.strip()
        return ReadWebpageResult(
            requested_url=url,
            url=result["url"],
            content=content[:MAX_CONTENT_CHARACTERS],
            content_truncated=len(content) > MAX_CONTENT_CHARACTERS,
            original_content_chars=len(content),
        )

    async def map(self, url: str, instructions: str) -> list[str]:
        url = validate_public_url(url)
        async with self.limiter.slot():
            response = await self.client.post(
                "https://api.tavily.com/map",
                headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
                json={
                    "url": url,
                    "instructions": instructions,
                    "limit": 20,
                    "max_depth": 2,
                    "allow_external": False,
                    "timeout": 15,
                },
                timeout=20,
                follow_redirects=False,
            )
        response.raise_for_status()
        payload = response.json()
        urls = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(urls, list):
            raise ValueError("Invalid Map response")
        return [validate_public_url(item) for item in urls[:20] if isinstance(item, str)]
