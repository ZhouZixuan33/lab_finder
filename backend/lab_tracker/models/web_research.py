"""URL-based finalizer contract; validation deliberately does not audit evidence."""

from typing import Annotated, Literal

from pydantic import Field, RootModel, model_validator

from lab_tracker.models.common import DomainModel
from lab_tracker.services.tag_taxonomy import ALLOWED_PROFESSOR_TAG_SET


class ResearchSuccess(DomainModel):
    status: Literal["success"]
    research_summary: str = Field(min_length=40, max_length=2000)
    tags: list[str] = Field(min_length=1, max_length=3)
    prospective_students_quote: str | None = Field(default=None, min_length=1, max_length=2000)
    prospective_students_source_url: str | None = Field(default=None, min_length=1)
    evidence_urls: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def check_fields(self) -> "ResearchSuccess":
        if len(set(self.tags)) != len(self.tags) or any(
            tag not in ALLOWED_PROFESSOR_TAG_SET for tag in self.tags
        ):
            raise ValueError("Use 1–3 distinct exact taxonomy tags")
        if (self.prospective_students_quote is None) != (
            self.prospective_students_source_url is None
        ):
            raise ValueError("Prospective quote and URL must both be present or both null")
        if any(not url.strip() for url in self.evidence_urls):
            raise ValueError("Evidence URLs must be nonempty")
        return self


class InsufficientEvidence(DomainModel):
    status: Literal["insufficient_evidence"]
    reason: str = Field(min_length=1, max_length=1000)


class WebResearchOutcome(
    RootModel[Annotated[ResearchSuccess | InsufficientEvidence, Field(discriminator="status")]]
):
    pass
