"""Server-owned Tavily client that returns a small sanitized result set."""

from typing import Any, Protocol

import httpx
from langchain_tavily import TavilySearch
from pydantic import SecretStr

from lab_tracker.models.research import SearchHit
from lab_tracker.services.rate_limit import SerialRateLimiter


class TavilyBackend(Protocol):
    async def ainvoke(self, tool_input: dict[str, Any]) -> Any: ...


class TavilyProvider:
    def __init__(
        self,
        backend: TavilyBackend | None = None,
        *,
        limiter: SerialRateLimiter | None = None,
        api_key: SecretStr | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client
        if backend is None and client is None:
            if api_key is None:
                raise ValueError("A Tavily API key is required")
            backend = TavilySearch(
                tavily_api_key=api_key.get_secret_value(),
                search_depth="basic",
                max_results=5,
                include_answer=False,
                include_raw_content=False,
                include_images=False,
                include_image_descriptions=False,
                include_favicon=False,
                auto_parameters=False,
                topic="general",
            )
        self._backend = backend
        self._limiter = limiter or SerialRateLimiter(1.0)
        self._api_key = api_key

    def __repr__(self) -> str:
        return "TavilyProvider(max_results=5, search_depth='basic')"

    async def search(self, query: str) -> list[SearchHit]:
        normalized_query = " ".join(query.split())
        if not normalized_query or len(normalized_query) > 500:
            raise ValueError("Tavily query must contain between 1 and 500 characters")

        async with self._limiter.slot():
            if self._client is not None:
                if self._api_key is None:
                    raise ValueError("A Tavily API key is required")
                response = await self._client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
                    json={
                        "query": normalized_query,
                        "search_depth": "basic",
                        "max_results": 5,
                        "include_answer": False,
                        "include_raw_content": False,
                    },
                    timeout=20,
                    follow_redirects=False,
                )
                response.raise_for_status()
                payload = response.json()
            else:
                payload = await self._backend.ainvoke({"query": normalized_query})
        if not isinstance(payload, dict):
            raise ValueError("Tavily returned an invalid response")

        results = payload.get("results")
        if not isinstance(results, list):
            return []

        hits: list[SearchHit] = []
        for result in results[:5]:
            if not isinstance(result, dict):
                continue
            title = str(result.get("title") or "").strip()
            url = str(result.get("url") or "").strip()
            if not title or not url:
                continue
            content = " ".join(str(result.get("content") or "").split())[:1_200]
            raw_score = result.get("score")
            score = float(raw_score) if isinstance(raw_score, int | float) else None
            hits.append(SearchHit(title=title, url=url, snippet=content, score=score))
        return hits
