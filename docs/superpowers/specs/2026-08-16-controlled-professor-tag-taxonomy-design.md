# Controlled Professor Tag Taxonomy Design

**Date:** 2026-08-16  
**Status:** Approved design, pending implementation

## 1. Objective

Replace freely generated, narrowly scoped professor tags with one to three broad,
consistent ECE research categories. Tags must remain useful for filtering the professor
list and must not vary merely because the LLM uses different terminology.

## 2. Controlled taxonomy

The only allowed professor tags are:

1. `Artificial Intelligence & Machine Learning`
2. `Computer Architecture & Systems`
3. `Networking & Distributed Systems`
4. `Security & Privacy`
5. `Signal Processing & Communications`
6. `Control, Robotics & Autonomous Systems`
7. `Circuits & Integrated Systems`
8. `Semiconductor Devices & Microelectronics`
9. `Electromagnetics, Optics & Photonics`
10. `Power & Energy Systems`
11. `Bioengineering & Biomedical Systems`
12. `Quantum Information & Computing`

Each professor must have at least one and at most three tags. The LLM must return the
category strings exactly as listed and may not create additional categories.

## 3. Prompt design

### 3.1 Research-agent prompt

Replace the requirement to gather evidence for `free-form tags` with a requirement to
gather enough evidence to select `1–3 controlled broad research categories`. The
research agent still gathers sources and does not make the final validated selection.

### 3.2 Finalizer prompt

The finalizer system prompt will include the complete taxonomy and these rules:

```text
Classify the professor's research into 1 to 3 broad research categories.

Allowed categories:
- Artificial Intelligence & Machine Learning
- Computer Architecture & Systems
- Networking & Distributed Systems
- Security & Privacy
- Signal Processing & Communications
- Control, Robotics & Autonomous Systems
- Circuits & Integrated Systems
- Semiconductor Devices & Microelectronics
- Electromagnetics, Optics & Photonics
- Power & Energy Systems
- Bioengineering & Biomedical Systems
- Quantum Information & Computing

Tagging rules:
1. Return only exact category names from the allowed list.
2. Select at least 1 and at most 3 categories.
3. Prefer the smallest number of categories that accurately represents the professor.
4. Map specific research topics to their broader parent category.
5. Do not return techniques, applications, paper topics, or narrowly scoped research
   terms as tags.
6. Do not create new categories.
7. Every selected category must be supported by the supplied evidence.

Examples:
- Congestion control, datacenter networking, host networks
  -> Networking & Distributed Systems
- CPU design, chiplets, memory hierarchy
  -> Computer Architecture & Systems
- Deep learning, computer vision, natural language processing
  -> Artificial Intelligence & Machine Learning
```

The examples teach abstraction rather than exhaustively mapping every research topic.

## 4. Deterministic enforcement

Prompt instructions are not the trust boundary. The structured result model will limit
`tags` to one through three items. Validation will normalize whitespace, remove exact
case-insensitive duplicates, and reject any remaining tag that is not an exact member
of the controlled taxonomy.

An invalid category causes `ResearchValidationError`. The existing finalizer retry loop
will receive the validation message and retry, up to its current limit. The backend will
not use fuzzy matching or silently remap an unrecognized category because that could
store an incorrect research classification.

The controlled taxonomy should live in one backend module and be imported by prompt
construction, model constraints where appropriate, validation, and tests. This avoids
duplicated category lists drifting apart.

## 5. Data flow

1. The research agent collects identity-matched research evidence and publications.
2. The finalizer maps evidence to one through three categories from the taxonomy.
3. Pydantic rejects an empty list or more than three values.
4. Deterministic validation rejects values outside the taxonomy.
5. Valid tags flow unchanged into professor insertion or an update proposal.
6. The existing professor-list tag filter displays only categories present in stored
   professor records.

## 6. Existing data

The change applies to newly researched professors and future single-professor update
proposals. It does not perform a bulk migration or silently rewrite existing professor
tags. Existing tags can be replaced later through the normal confirmed single-professor
update workflow.

## 7. Error handling and diagnostics

- Invalid categories are treated as finalizer validation errors, not accepted output.
- Repeated validation failure ends the professor research run using the existing failure
  path.
- Existing LLM call and professor research diagnostics remain unchanged; no prompt or
  evidence content is added to logs.

## 8. Testing

Tests will verify:

- the finalizer prompt contains every allowed category and the 1–3 rule;
- the structured model rejects zero tags and more than three tags;
- validation accepts one to three exact controlled categories;
- validation rejects narrow, invented, or misspelled categories;
- duplicate categories collapse before the final one-to-three check;
- a representative networking/systems result remains valid;
- existing research graph retry behavior handles invalid LLM categories;
- all existing API and job tests continue to pass.

## 9. Example outcome

For research involving datacenter networking, host networks, chiplets, and CPU network
architecture, the expected tags are:

```json
{
  "tags": [
    "Networking & Distributed Systems",
    "Computer Architecture & Systems"
  ]
}
```

Terms such as `Congestion Control`, `Host Networks`, `Chiplets`, and `IO Memory
Protection` remain suitable summary or publication concepts but are not stored as tags.
