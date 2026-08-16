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


class ProfessorResearchResult(DomainModel):
    """Structured output requested from the finalizer model.

    URLs and publications are selected only by opaque IDs. They are resolved by
    deterministic validation after the model returns this object.
    """

    research_summary: str = Field(min_length=40, max_length=2_000)
    tags: list[str] = Field(min_length=1, max_length=3)
    homepage_source_id: str | None = None
    lab_source_id: str | None = None
    publication_source_ids: list[str] = Field(default_factory=list, max_length=25)
    evidence_source_ids: list[str] = Field(min_length=1, max_length=5)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ValidatedProfessorResearch(DomainModel):
    research_summary: str
    tags: list[str]
    homepage_url: str | None = None
    lab_url: str | None = None
    publications: list[OpenAlexPublication] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    confidence: float | None = None
