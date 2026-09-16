"""Deterministic professor identity normalization and matching."""

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

UIUC_ECE_AFFILIATION = "University of Illinois Urbana-Champaign Electrical and Computer Engineering"
TRACKING_QUERY_KEYS = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})


class CandidateIdentity(Protocol):
    name: str
    email: str | None
    official_profile_url: str
    affiliation: str


@dataclass(frozen=True)
class ExistingProfessorIdentity:
    professor_id: int
    name: str
    email: str | None
    official_profile_url: str
    affiliation: str = UIUC_ECE_AFFILIATION


class AmbiguousIdentityError(ValueError):
    def __init__(self, field: str, professor_ids: list[int]) -> None:
        super().__init__(f"Ambiguous professor identity by {field}: {professor_ids}")
        self.field = field
        self.professor_ids = professor_ids


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    words = re.sub(r"[^a-z0-9]+", " ", without_marks.casefold())
    return " ".join(words.split())


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"^mailto:", "", value.strip(), flags=re.IGNORECASE)
    normalized = normalized.split("?", 1)[0].strip().casefold()
    return normalized or None


def normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    scheme = parsed.scheme.casefold() or "https"
    hostname = (parsed.hostname or "").casefold()
    port = parsed.port
    uses_default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    if port is not None and not uses_default_port:
        hostname = f"{hostname}:{port}"

    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")

    query_items = [
        (key, item_value)
        for key, item_value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in TRACKING_QUERY_KEYS
    ]
    query = urlencode(sorted(query_items))
    return urlunsplit((scheme, hostname, path if path != "/" else "", query, ""))


def _normalize_affiliation(value: str) -> str:
    return normalize_name(value)


class IdentityIndex:
    def __init__(self, identities: Iterable[ExistingProfessorIdentity]) -> None:
        self._by_url: dict[str, list[int]] = defaultdict(list)
        self._by_email: dict[str, list[int]] = defaultdict(list)
        self._by_name_and_affiliation: dict[tuple[str, str], list[int]] = defaultdict(list)

        for identity in identities:
            self._by_url[normalize_url(identity.official_profile_url)].append(identity.professor_id)
            email = normalize_email(identity.email)
            if email:
                self._by_email[email].append(identity.professor_id)
            name_key = (normalize_name(identity.name), _normalize_affiliation(identity.affiliation))
            self._by_name_and_affiliation[name_key].append(identity.professor_id)

    def match(self, candidate: CandidateIdentity) -> int | None:
        url_matches = self._by_url.get(normalize_url(candidate.official_profile_url), [])
        if url_matches:
            return self._single_match("official_profile_url", url_matches)

        email = normalize_email(candidate.email)
        if email:
            email_matches = self._by_email.get(email, [])
            if email_matches:
                return self._single_match("email", email_matches)

        name_key = (normalize_name(candidate.name), _normalize_affiliation(candidate.affiliation))
        name_matches = self._by_name_and_affiliation.get(name_key, [])
        if name_matches:
            return self._single_match("name_and_affiliation", name_matches)
        return None

    @staticmethod
    def _single_match(field: str, professor_ids: list[int]) -> int:
        unique_ids = sorted(set(professor_ids))
        if len(unique_ids) != 1:
            raise AmbiguousIdentityError(field, unique_ids)
        return unique_ids[0]
