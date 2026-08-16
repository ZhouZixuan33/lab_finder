"""Single-professor update proposal models."""

from datetime import datetime
from typing import Any

from pydantic import Field

from lab_tracker.models.common import DomainModel, ProposalStatus


class ProposalCreate(DomainModel):
    job_id: str = Field(min_length=1)
    professor_id: int
    old_values: dict[str, Any] = Field(default_factory=dict)
    new_values: dict[str, Any] = Field(default_factory=dict)
    publication_diff: dict[str, Any] = Field(default_factory=dict)
    source_urls: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ProposalRecord(ProposalCreate):
    id: int
    status: ProposalStatus
    created_at: datetime
    resolved_at: datetime | None = None
