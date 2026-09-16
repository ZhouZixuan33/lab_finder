import pytest

from lab_tracker.services.discovery import FacultyCandidate
from lab_tracker.services.identity import (
    AmbiguousIdentityError,
    ExistingProfessorIdentity,
    IdentityIndex,
    normalize_email,
    normalize_name,
    normalize_url,
)


def candidate(
    *,
    name: str = "José A. Example",
    email: str | None = "JOSE@Illinois.edu",
    profile_url: str = "https://ECE.Illinois.edu/about/directory/faculty/jose/?utm_source=test#bio",
) -> FacultyCandidate:
    return FacultyCandidate(
        name=name,
        title="Assistant Professor",
        email=email,
        official_profile_url=profile_url,
    )


def test_identity_normalization_handles_case_accents_and_tracking_parameters() -> None:
    assert normalize_name("  José-A.  Example ") == "jose a example"
    assert normalize_email(" MAILTO:JOSE@Illinois.edu ") == "jose@illinois.edu"
    assert normalize_url(
        "HTTPS://ECE.Illinois.edu:443/about//directory/faculty/jose/?utm_source=test#bio"
    ) == "https://ece.illinois.edu/about/directory/faculty/jose"


def test_identity_matching_uses_profile_then_email_then_name() -> None:
    identities = [
        ExistingProfessorIdentity(
            professor_id=1,
            name="Different Person",
            email="different@illinois.edu",
            official_profile_url="https://ece.illinois.edu/about/directory/faculty/jose",
        ),
        ExistingProfessorIdentity(
            professor_id=2,
            name="José A. Example",
            email="jose@illinois.edu",
            official_profile_url="https://ece.illinois.edu/about/directory/faculty/other",
        ),
    ]
    index = IdentityIndex(identities)

    assert index.match(candidate()) == 1
    assert index.match(
        candidate(profile_url="https://ece.illinois.edu/about/directory/faculty/new")
    ) == 2
    assert index.match(
        candidate(
            email=None,
            profile_url="https://ece.illinois.edu/about/directory/faculty/new",
        )
    ) == 2


def test_ambiguous_email_or_name_fails_only_that_candidate() -> None:
    index = IdentityIndex(
        [
            ExistingProfessorIdentity(
                professor_id=1,
                name="Same Person",
                email="shared@illinois.edu",
                official_profile_url="https://ece.illinois.edu/one",
            ),
            ExistingProfessorIdentity(
                professor_id=2,
                name="Same Person",
                email="shared@illinois.edu",
                official_profile_url="https://ece.illinois.edu/two",
            ),
        ]
    )

    with pytest.raises(AmbiguousIdentityError):
        index.match(
            candidate(
                name="Same Person",
                email="shared@illinois.edu",
                profile_url="https://ece.illinois.edu/new",
            )
        )
