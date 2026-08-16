# Controlled Professor Tag Taxonomy Implementation Plan

## Goal

Make every LangGraph-researched professor return one to three exact, broad research
categories from the approved 12-category taxonomy, while preserving existing stored
data and the current REST API/database shapes.

## Scope and invariants

- Constrain only the LLM research result boundary and its deterministic validation.
- Do not add or migrate database tables.
- Do not rewrite existing professor records in bulk.
- Do not restrict `ProfessorCreate` or repository read models, because they must still
  deserialize existing free-form tags until those records are refreshed normally.
- Do not change frontend filtering, REST endpoints, job behavior, or update-confirmation
  semantics.

## Task 1: Add one canonical taxonomy module

Create `backend/lab_tracker/services/tag_taxonomy.py` containing:

- an ordered tuple with the 12 approved display strings;
- an immutable membership set derived from the tuple;
- no LLM, database, or HTTP dependencies.

Add `backend/tests/unit/test_tag_taxonomy.py` first. Verify that the tuple contains the
12 approved unique, non-empty category names and that the membership set matches it.

This module becomes the only source of taxonomy values. Prompt construction,
validation, and tests import it rather than duplicating the category list.

## Task 2: Constrain the structured LLM result

Update `ProfessorResearchResult.tags` in
`backend/lab_tracker/models/research.py` from a 1–12 list to a 1–3 list.

Add model tests that prove:

- one and three tags are accepted structurally;
- zero tags are rejected;
- four tags are rejected before deterministic validation.

Do not add the taxonomy membership rule to the Pydantic field. Membership depends on
the service taxonomy and belongs at the existing research-validation boundary, which
avoids coupling domain model imports back to a service module.

## Task 3: Put controlled classification rules in both research prompts

Update `backend/lab_tracker/services/research_prompts.py`:

1. Change the research-agent wording from `free-form tags` to `1–3 controlled broad
   research categories` so the agent knows when it has sufficient evidence.
2. Render the canonical taxonomy into the finalizer system prompt.
3. Add the approved rules: exact allowed strings, one-to-three limit, prefer fewer
   accurate categories, map subtopics upward, evidence requirement, and prohibition on
   new/narrow tags.
4. Include the three approved mapping examples for networking, architecture, and AI.

Add focused prompt tests in `backend/tests/unit/test_research_prompts.py` that assert:

- every canonical taxonomy item occurs in the finalizer system prompt;
- the one-to-three and exact-category rules are present;
- the agent prompt no longer requests free-form tags;
- verified evidence still reaches the human message while prompt-injection text remains
  excluded by the existing page extraction boundary.

Prompt tests should assert required concepts and canonical values rather than one large
snapshot, so harmless wording changes do not make them brittle.

## Task 4: Enforce exact membership during deterministic validation

Update `backend/lab_tracker/services/research_validation.py` after writing failing tests
in `backend/tests/unit/test_research_validation.py`.

Validation behavior:

1. Normalize surrounding and repeated whitespace as today.
2. Remove case-insensitive duplicates while preserving first-seen order.
3. Reject every remaining value not exactly equal, including capitalization, to one of
   the canonical taxonomy strings.
4. Return the deduplicated categories unchanged when all are allowed.

Use a concise `ResearchValidationError` that identifies invalid values and reminds the
finalizer to select from the allowed taxonomy. Do not fuzzy-match, translate, or silently
map values such as `Congestion Control` or `computer architecture & systems`.

Tests will cover:

- valid one-, two-, and three-category results;
- duplicate allowed categories collapsing in stable order;
- a narrow tag such as `Congestion Control` being rejected;
- an invented or incorrectly capitalized category being rejected;
- existing source-ID, identity, link, and publication validation remaining unchanged.

## Task 5: Update graph fixtures and prove retry behavior

Update research-result fixtures in `backend/tests/unit/test_research_graph.py` to use
canonical categories, especially:

- `Networking & Distributed Systems`;
- `Computer Architecture & Systems`.

Extend the existing finalizer retry test so its first structurally valid attempt contains
an invalid narrow tag, then verify:

- deterministic validation rejects it;
- the validation feedback is included in the next finalizer invocation;
- a subsequent canonical result succeeds;
- three invalid results still end in the existing `ResearchGraphError` path.

Only update unrelated integration fixtures when they directly exercise the LangGraph
validation boundary. Repository/API fixtures may keep legacy free-form tags because
backward-compatible storage and filtering are explicitly in scope.

## Task 6: Documentation and verification

Update the README research-pipeline description to state that LLM-generated professor
tags use the 12-category controlled taxonomy with one to three categories per professor.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_tag_taxonomy.py -q
.\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_research_prompts.py -q
.\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_research_validation.py -q
.\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_research_graph.py -q
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Use an explicit writable pytest base directory if the Windows system temp directory is
unavailable. A real one-professor LLM smoke test is optional and requires a separate
explicit authorization because it consumes external API quota. If run, it must not
write the professor to SQLite and must verify that every printed tag belongs to the
canonical taxonomy.

## Commit boundaries

1. `feat: define controlled professor tag taxonomy`
2. `feat: enforce controlled professor research tags`
3. `docs: document controlled professor tags`

Existing unrelated workspace changes, including `.env.example`, `tmp/`, and unrelated
spec files, must remain untouched and unstaged.
