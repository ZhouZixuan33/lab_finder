from lab_tracker.services.tag_taxonomy import (
    ALLOWED_PROFESSOR_TAG_SET,
    ALLOWED_PROFESSOR_TAGS,
)


def test_controlled_professor_taxonomy_has_the_approved_unique_categories() -> None:
    assert ALLOWED_PROFESSOR_TAGS == (
        "AI Algorithms & Learning Theory",
        "NLP, LLMs & Generative AI",
        "Computer Vision & Graphics",
        "AI Infrastructure & Systems",
        "Robotics, Control & Embodied AI",
        "Computer Architecture & Hardware",
        "Operating & Distributed Systems",
        "Networking & Mobile Computing",
        "Data Management & Mining",
        "Programming Languages & Software Engineering",
        "Security & Privacy",
        "Human-Computer Interaction & Computing Education",
        "Algorithms & Computational Theory",
        "Scientific & Numerical Computing",
        "Signal Processing & Communications",
        "Electronics, Semiconductors & Photonics",
        "Quantum Computing & Information",
        "Biomedical & Computational Biology",
        "Power & Energy Systems",
    )
    assert len(ALLOWED_PROFESSOR_TAGS) == len(set(ALLOWED_PROFESSOR_TAGS))
    assert all(tag.strip() == tag and tag for tag in ALLOWED_PROFESSOR_TAGS)
    assert frozenset(ALLOWED_PROFESSOR_TAGS) == ALLOWED_PROFESSOR_TAG_SET
