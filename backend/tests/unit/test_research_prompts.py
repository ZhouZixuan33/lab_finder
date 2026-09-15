from lab_tracker.models.research import ResearchIdentity
from lab_tracker.services.research_prompts import (
    build_agent_messages,
    build_finalizer_messages,
)
from lab_tracker.services.tag_taxonomy import ALLOWED_PROFESSOR_TAGS


def identity() -> ResearchIdentity:
    return ResearchIdentity(
        name="Alice Systems",
        email="alice@illinois.edu",
        title="Professor",
        affiliation="University of Illinois Urbana-Champaign",
        official_profile_url="https://ece.illinois.edu/about/directory/faculty/alice",
    )


def test_agent_prompt_requests_controlled_broad_categories() -> None:
    messages = build_agent_messages(identity(), official_source_id="source_001")
    prompt = str(messages[0].content)

    assert "free-form tags" not in prompt
    assert "1–3 controlled broad research categories" in prompt


def test_finalizer_prompt_contains_the_complete_taxonomy_and_selection_rules() -> None:
    messages = build_finalizer_messages(
        identity(),
        pages=[],
        previous_errors=[],
    )
    prompt = str(messages[0].content)

    for tag in ALLOWED_PROFESSOR_TAGS:
        assert f"- {tag}" in prompt
    assert "1 to 3 broad research categories" in prompt
    assert "exact category names" in prompt
    assert "Do not create new categories" in prompt
    assert "Congestion control" in prompt
    assert "Networking & Mobile Computing" in prompt
    assert "Category definitions" in prompt
    assert "Using an existing AI model" in prompt
    assert "Model compression or quantization alone is not proof" in prompt
    assert "Do not automatically add AI Algorithms & Learning Theory" in prompt
    assert "Do not fill unused slots" in prompt
