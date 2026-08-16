from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from lab_tracker.models.research import ResearchIdentity
from lab_tracker.services.openalex_provider import (
    AmbiguousOpenAlexAuthorError,
    OpenAlexProvider,
)


class FakeOpenAlexHttp:
    def __init__(
        self,
        author_results: list[dict[str, Any]],
        work_results: list[dict[str, Any]],
    ) -> None:
        self.author_results = author_results
        self.work_results = work_results
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get(self, url: str, **kwargs: object) -> httpx.Response:
        params = dict(kwargs["params"])  # type: ignore[arg-type]
        self.calls.append((url, params))
        request = httpx.Request("GET", url, params=params)
        results = self.author_results if url.endswith("/authors") else self.work_results
        payload = {"results": results}
        return httpx.Response(200, json=payload, request=request)


def identity() -> ResearchIdentity:
    return ResearchIdentity(
        name="Alice Systems",
        email="alice@illinois.edu",
        title="Professor",
        affiliation="University of Illinois Urbana-Champaign Electrical and Computer Engineering",
        official_profile_url="https://ece.illinois.edu/about/directory/faculty/alice",
    )


@pytest.mark.asyncio
async def test_openalex_disambiguates_uiuc_author_uses_three_year_window_and_caches() -> None:
    http = FakeOpenAlexHttp(
        author_results=[
            {
                "id": "https://openalex.org/A1",
                "display_name": "Alice Systems",
                "last_known_institutions": [
                    {"display_name": "University of Illinois Urbana-Champaign"}
                ],
                "affiliations": [],
                "works_count": 10,
                "cited_by_count": 100,
            },
            {
                "id": "https://openalex.org/A2",
                "display_name": "Alice Systems",
                "last_known_institutions": [{"display_name": "Another University"}],
                "affiliations": [],
                "works_count": 50,
                "cited_by_count": 500,
            },
        ],
        work_results=[
            {
                "id": "https://openalex.org/W1",
                "title": "Reliable Accelerators",
                "publication_year": 2026,
                "doi": "https://doi.org/10.1000/example",
                "cited_by_count": 7,
                "primary_location": {
                    "landing_page_url": "https://example.edu/paper",
                    "source": {"display_name": "ExampleConf"},
                },
                "abstract_inverted_index": {"Reliable": [0], "systems": [1]},
            },
            {
                "id": "https://openalex.org/W2",
                "title": "Reliable Accelerators",
                "publication_year": 2026,
                "doi": None,
                "cited_by_count": 1,
                "primary_location": None,
                "abstract_inverted_index": None,
            },
        ],
    )
    provider = OpenAlexProvider(
        http,
        api_key=SecretStr("openalex-secret"),
        current_year=2026,
    )

    publications = await provider.get_recent_publications(identity())
    cached = await provider.get_recent_publications(identity())

    assert len(publications) == 1
    assert publications[0].openalex_id == "W1"
    assert publications[0].abstract == "Reliable systems"
    assert publications[0].doi == "10.1000/example"
    assert cached == publications
    assert len(http.calls) == 2
    authors_call, works_call = http.calls
    assert authors_call[0].endswith("/authors")
    assert works_call[1]["filter"] == "authorships.author.id:A1,from_publication_date:2024-01-01"
    assert works_call[1]["sort"] == "publication_date:desc"
    assert "openalex-secret" not in repr(publications)


@pytest.mark.asyncio
async def test_openalex_rejects_ambiguous_uiuc_author_match() -> None:
    shared = {
        "display_name": "Alice Systems",
        "last_known_institutions": [
            {"display_name": "University of Illinois Urbana-Champaign"}
        ],
        "affiliations": [],
        "works_count": 10,
        "cited_by_count": 100,
    }
    http = FakeOpenAlexHttp(
        author_results=[
            {**shared, "id": "https://openalex.org/A1"},
            {**shared, "id": "https://openalex.org/A2"},
        ],
        work_results=[],
    )
    provider = OpenAlexProvider(http, current_year=2026)

    with pytest.raises(AmbiguousOpenAlexAuthorError):
        await provider.get_recent_publications(identity())

    assert len(http.calls) == 1
