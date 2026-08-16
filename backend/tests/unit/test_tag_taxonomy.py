from lab_tracker.services.tag_taxonomy import (
    ALLOWED_PROFESSOR_TAG_SET,
    ALLOWED_PROFESSOR_TAGS,
)


def test_controlled_professor_taxonomy_has_the_approved_unique_categories() -> None:
    assert ALLOWED_PROFESSOR_TAGS == (
        "Artificial Intelligence & Machine Learning",
        "Computer Architecture & Systems",
        "Networking & Distributed Systems",
        "Security & Privacy",
        "Signal Processing & Communications",
        "Control, Robotics & Autonomous Systems",
        "Circuits & Integrated Systems",
        "Semiconductor Devices & Microelectronics",
        "Electromagnetics, Optics & Photonics",
        "Power & Energy Systems",
        "Bioengineering & Biomedical Systems",
        "Quantum Information & Computing",
    )
    assert len(ALLOWED_PROFESSOR_TAGS) == len(set(ALLOWED_PROFESSOR_TAGS))
    assert all(tag.strip() == tag and tag for tag in ALLOWED_PROFESSOR_TAGS)
    assert frozenset(ALLOWED_PROFESSOR_TAGS) == ALLOWED_PROFESSOR_TAG_SET
