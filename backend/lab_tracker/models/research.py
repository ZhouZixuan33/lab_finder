"""Models exchanged by bounded research providers and LangChain tools."""

from pydantic import Field

from lab_tracker.models.common import DomainModel


class ResearchIdentity(DomainModel):
    name: str = Field(min_length=1)
    email: str | None = None
    title: str = Field(min_length=1)
    affiliation: str = Field(min_length=1)
    official_profile_url: str = Field(min_length=1)


class SearchHit(DomainModel):
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    snippet: str = ""
    score: float | None = None


class RegisteredSource(SearchHit):
    source_id: str
    candidate_id: str


class IdentitySignals(DomainModel):
    name_match: bool = False
    email_match: bool = False
    affiliation_match: bool = False


class ExtractedPage(DomainModel):
    source_id: str
    candidate_id: str
    url: str
    title: str | None = None
    text: str
    identity_signals: IdentitySignals


class OpenAlexPublication(DomainModel):
    source_id: str
    openalex_id: str
    title: str = Field(min_length=1)
    year: int
    venue: str | None = None
    publication_url: str | None = None
    doi: str | None = None
    cited_by_count: int = Field(default=0, ge=0)
    abstract: str | None = None
