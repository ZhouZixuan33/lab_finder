"""Identity-bound OpenAlex author disambiguation and recent-work retrieval."""

import re
from datetime import date
from typing import Any, Protocol

from httpx import Response
from pydantic import SecretStr

from lab_tracker.models.research import OpenAlexPublication, ResearchIdentity
from lab_tracker.services.identity import normalize_name

OPENALEX_API_BASE_URL = "https://api.openalex.org"
AUTHOR_SELECT = "id,display_name,last_known_institutions,affiliations,works_count,cited_by_count"
WORK_SELECT = (
    "id,title,publication_year,publication_date,primary_location,doi,"
    "cited_by_count,abstract_inverted_index"
)


class OpenAlexError(RuntimeError):
    pass


class OpenAlexAuthorNotFoundError(OpenAlexError):
    pass


class AmbiguousOpenAlexAuthorError(OpenAlexError):
    pass


class OpenAlexHttpClient(Protocol):
    async def get(self, url: str, **kwargs: object) -> Response: ...


def _short_openalex_id(value: object) -> str:
    return str(value or "").rstrip("/").rsplit("/", 1)[-1]


def _institution_names(author: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for institution in author.get("last_known_institutions") or []:
        if isinstance(institution, dict) and institution.get("display_name"):
            names.append(str(institution["display_name"]))
    for affiliation in author.get("affiliations") or []:
        if not isinstance(affiliation, dict):
            continue
        institution = affiliation.get("institution")
        if isinstance(institution, dict) and institution.get("display_name"):
            names.append(str(institution["display_name"]))
    return names


def _abstract_from_inverted_index(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    positioned_words: list[tuple[int, str]] = []
    for word, positions in value.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                positioned_words.append((position, word))
    if not positioned_words:
        return None
    positioned_words.sort()
    return " ".join(word for _, word in positioned_words)[:2_000]


class OpenAlexProvider:
    def __init__(
        self,
        http_client: OpenAlexHttpClient,
        *,
        api_key: SecretStr | None = None,
        current_year: int | None = None,
    ) -> None:
        self.http_client = http_client
        self._api_key = api_key
        self.current_year = current_year or date.today().year
        self._cache: dict[tuple[str, str, int], list[OpenAlexPublication]] = {}

    def __repr__(self) -> str:
        return f"OpenAlexProvider(current_year={self.current_year})"

    async def get_recent_publications(
        self,
        identity: ResearchIdentity,
    ) -> list[OpenAlexPublication]:
        cache_key = (
            normalize_name(identity.name),
            normalize_name(identity.affiliation),
            self.current_year,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return [publication.model_copy() for publication in cached]

        author_id = await self._find_author(identity)
        since_year = self.current_year - 2
        response = await self.http_client.get(
            f"{OPENALEX_API_BASE_URL}/works",
            params=self._with_api_key(
                {
                    "filter": (
                        f"authorships.author.id:{author_id},"
                        f"from_publication_date:{since_year}-01-01"
                    ),
                    "sort": "publication_date:desc",
                    "per-page": 25,
                    "select": WORK_SELECT,
                }
            ),
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", []) if isinstance(payload, dict) else []
        publications = self._parse_works(results)
        self._cache[cache_key] = publications
        return [publication.model_copy() for publication in publications]

    async def _find_author(self, identity: ResearchIdentity) -> str:
        response = await self.http_client.get(
            f"{OPENALEX_API_BASE_URL}/authors",
            params=self._with_api_key(
                {
                    "search": identity.name,
                    "per-page": 10,
                    "select": AUTHOR_SELECT,
                }
            ),
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", []) if isinstance(payload, dict) else []
        target_name = normalize_name(identity.name)
        candidates: list[tuple[int, str]] = []
        for author in results:
            if not isinstance(author, dict):
                continue
            display_name = normalize_name(str(author.get("display_name") or ""))
            name_score = 5 if display_name == target_name else 0
            if not name_score and (display_name in target_name or target_name in display_name):
                name_score = 3
            institution_match = any(
                "university of illinois urbana champaign" in normalize_name(name)
                for name in _institution_names(author)
            )
            if name_score and institution_match:
                candidates.append((name_score + 5, _short_openalex_id(author.get("id"))))

        if not candidates:
            raise OpenAlexAuthorNotFoundError(f"No UIUC OpenAlex author found for {identity.name}")
        best_score = max(score for score, _ in candidates)
        best_ids = sorted({author_id for score, author_id in candidates if score == best_score})
        if len(best_ids) != 1:
            raise AmbiguousOpenAlexAuthorError(
                f"Multiple UIUC OpenAlex authors matched {identity.name}: {best_ids}"
            )
        return best_ids[0]

    def _with_api_key(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._api_key is not None:
            return {**params, "api_key": self._api_key.get_secret_value()}
        return params

    @staticmethod
    def _parse_works(results: object) -> list[OpenAlexPublication]:
        if not isinstance(results, list):
            return []
        publications: list[OpenAlexPublication] = []
        seen: set[tuple[str, int]] = set()
        for work in results:
            if not isinstance(work, dict):
                continue
            title = " ".join(str(work.get("title") or "").split())
            year = work.get("publication_year")
            if not title or not isinstance(year, int):
                continue
            dedupe_key = (re.sub(r"\W+", " ", title.casefold()).strip(), year)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            location = work.get("primary_location")
            source = location.get("source") if isinstance(location, dict) else None
            venue = source.get("display_name") if isinstance(source, dict) else None
            publication_url = (
                location.get("landing_page_url") if isinstance(location, dict) else None
            )
            openalex_id = _short_openalex_id(work.get("id"))
            raw_doi = str(work.get("doi") or "").strip() or None
            doi = (
                re.sub(r"^https?://doi\.org/", "", raw_doi, flags=re.IGNORECASE)
                if raw_doi
                else None
            )
            cited_by_count = work.get("cited_by_count")
            publications.append(
                OpenAlexPublication(
                    source_id=f"openalex:{openalex_id}",
                    openalex_id=openalex_id,
                    title=title,
                    year=year,
                    venue=str(venue) if venue else None,
                    publication_url=str(publication_url or work.get("id") or "") or None,
                    doi=doi,
                    cited_by_count=cited_by_count if isinstance(cited_by_count, int) else 0,
                    abstract=_abstract_from_inverted_index(work.get("abstract_inverted_index")),
                )
            )
        return publications
