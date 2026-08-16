"""Job-local registry that prevents model-selected arbitrary URL fetching."""

from ipaddress import ip_address
from urllib.parse import urlsplit

from lab_tracker.models.research import RegisteredSource, SearchHit
from lab_tracker.services.identity import normalize_url


class SourceRegistryError(ValueError):
    pass


class UnsafeSourceError(SourceRegistryError):
    pass


class UnknownSourceError(SourceRegistryError):
    pass


class SourceLimitError(SourceRegistryError):
    pass


def _validate_public_http_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise UnsafeSourceError("Only HTTP and HTTPS research sources are allowed")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeSourceError("Research source URL has an invalid authority")

    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise UnsafeSourceError("Local research source hosts are not allowed")
    try:
        address = ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise UnsafeSourceError("Non-public research source addresses are not allowed")
    return normalize_url(url)


class CandidateSourceRegistry:
    def __init__(self, *, max_sources: int = 15) -> None:
        if max_sources < 1:
            raise ValueError("max_sources must be positive")
        self.max_sources = max_sources
        self._by_id: dict[str, RegisteredSource] = {}
        self._id_by_url: dict[str, str] = {}

    def register_hit(self, hit: SearchHit) -> RegisteredSource:
        normalized_url = _validate_public_http_url(hit.url)
        existing_id = self._id_by_url.get(normalized_url)
        if existing_id is not None:
            return self._by_id[existing_id]
        if len(self._by_id) >= self.max_sources:
            raise SourceLimitError("Research source registry limit reached")

        sequence = len(self._by_id) + 1
        source = RegisteredSource(
            source_id=f"source_{sequence:03d}",
            candidate_id=f"candidate_{sequence:03d}",
            title=hit.title,
            url=normalized_url,
            snippet=hit.snippet,
            score=hit.score,
        )
        self._by_id[source.source_id] = source
        self._id_by_url[normalized_url] = source.source_id
        return source

    def register_hits(self, hits: list[SearchHit]) -> list[RegisteredSource]:
        registered: list[RegisteredSource] = []
        returned_ids: set[str] = set()
        for hit in hits:
            try:
                source = self.register_hit(hit)
            except UnsafeSourceError:
                continue
            if source.source_id not in returned_ids:
                registered.append(source)
                returned_ids.add(source.source_id)
        return registered

    def get(self, source_id: str) -> RegisteredSource:
        try:
            return self._by_id[source_id]
        except KeyError as error:
            raise UnknownSourceError(f"Unknown research source ID: {source_id}") from error

    def all(self) -> list[RegisteredSource]:
        return list(self._by_id.values())
