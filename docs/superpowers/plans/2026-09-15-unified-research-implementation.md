# Unified research graph implementation

Approved design: ../specs/2026-09-15-shared-state-research-graph-design.md

1. Add URL-based structured research outcomes, bounded Read/Map adapters and direct production Search requests without hidden retries.
2. Implement one sequential LangGraph with separate homepage/research messages, unchanged homepage discovery prompt, explicit handoff cleanup, shared ten-request and 120-second limits, and no page cache.
3. Add evidence-only finalization with success/insufficient_evidence branches, schema/taxonomy checks only, and one correction attempt.
4. Route new and refresh orchestration through this graph; retain OpenAlex enrichment and persistence outside it.
5. Test graph routing, scope of tools, repeated reads, truncation, limits, cancellation, schema correction and publication isolation. Run affected tests, backend regression suite and lint.

Do not change unrelated workspace files or live data. No live paid provider calls are required for validation.

Completed: steps 1–5. Validation: 191 backend tests passed; Ruff and git diff --check passed. Full suite required running outside the sandbox because pytest temporary-directory access was denied. No real providers or existing professor records were invoked.
