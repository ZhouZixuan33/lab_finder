"""Inputs and results for personal homepage discovery."""

from ipaddress import ip_address
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from lab_tracker.models.common import DomainModel


def validate_public_url(value: str) -> str:
    """Reject non-web URLs, credentials and explicit local addresses."""
    value = value.strip()
    parsed = urlsplit(value)
    host = (parsed.hostname or "").rstrip(".").lower()
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or host == "localhost"
        or host.endswith((".localhost", ".local"))
        or any(character.isspace() for character in value)
        or "\\" in value
    ):
        raise ValueError("A public HTTP or HTTPS URL without credentials is required")
    # Accessing port also validates malformed port values.
    _ = parsed.port
    try:
        address = ip_address(host)
    except ValueError:
        if "." not in host or host.replace(".", "").isdigit():
            raise ValueError("A public hostname is required") from None
    else:
        if not address.is_global:
            raise ValueError("Private and loopback IP addresses are not allowed")
    return value


class SearchWebInput(DomainModel):
    query: str = Field(
        min_length=1,
        max_length=500,
        description="A focused query using the professor's name, affiliation and homepage terms.",
    )


class ReadWebpageInput(DomainModel):
    url: str = Field(
        pattern=r"^https?://",
        description="One absolute public HTTP/HTTPS URL from the task, search or page content.",
    )

    @field_validator("url")
    @classmethod
    def public_url(cls, value: str) -> str:
        return validate_public_url(value)


class ReadWebpageResult(DomainModel):
    requested_url: str
    url: str
    content: str = Field(min_length=1)
    truncated: bool = False
    content_truncated: bool = False
    original_content_chars: int | None = None

    @field_validator("requested_url", "url")
    @classmethod
    def public_url(cls, value: str) -> str:
        return validate_public_url(value)


class HomepageResult(DomainModel):
    personal_homepage_url: str | None = Field(
        description="The professor's verified personal homepage URL, or null if unconfirmed."
    )
