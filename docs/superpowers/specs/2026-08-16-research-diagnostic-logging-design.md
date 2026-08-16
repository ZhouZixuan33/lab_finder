# Research Diagnostic Logging Design

## 1. Purpose

Add safe, terminal-visible diagnostics for professor research jobs so a developer can:

- see the structured professor information produced by the research pipeline;
- prove whether each LLM call was actually attempted;
- distinguish research-agent calls from structured-finalizer calls;
- see call success, failure, and duration without exposing secrets or oversized content.

This feature is diagnostic only. It does not change discovery, validation, persistence, proposal, or application behavior.

## 2. Output destination and format

Diagnostics are emitted at `INFO` level to the same PowerShell terminal that runs:

```powershell
.venv\Scripts\python.exe -m lab_tracker
```

The implementation uses Python's standard `logging` module and a dedicated `lab_tracker.research` logger. Each event is one compact line with a stable event name and JSON-compatible fields so it remains readable and searchable.

There is no log file, database log table, or browser-only console output in this scope.

## 3. LLM call events

Logging is placed immediately around the two real model invocation boundaries in `ProfessorResearchGraph`:

- `agent_model.ainvoke(...)` emits phase `research_agent`;
- `finalizer_model.ainvoke(...)` emits phase `finalizer`.

Every attempted invocation emits:

1. `llm_call.started` immediately before `ainvoke`;
2. either `llm_call.completed` after a successful return, or `llm_call.failed` when the invocation raises.

Fields:

| Field | Meaning |
| --- | --- |
| `professor` | Fixed professor identity for this graph run. |
| `phase` | `research_agent` or `finalizer`. |
| `attempt` | One-based call number within that phase. |
| `duration_ms` | Monotonic elapsed time, present on completion or failure. |
| `tool_calls` | Number of requested tool calls, when an agent response succeeds. |
| `error_type` | Exception class name on failure. |

The presence of `llm_call.started` is the authoritative proof that application code reached an actual model invocation. Provider-side acceptance is shown by `llm_call.completed`; authentication, quota, transport, and provider errors produce `llm_call.failed`.

## 4. Extracted professor event

After the LangGraph result passes business validation and immediately before the per-professor database write, discovery emits `professor.extracted` with one structured JSON payload:

- `name`
- `title`
- `email`
- `homepage_url`
- `lab_url`
- `research_summary`
- `tags`
- recent publications limited to `title`, `year`, `venue`, and `publication_url`
- `source_urls`
- `confidence`

The same event is emitted for a successful single-professor check before difference calculation. A validated result may therefore be inspected even when no database difference exists.

If research fails before validation, the system emits `professor.research_failed` with professor name, error type, and the existing sanitized job error message. It does not emit a partial professor payload.

## 5. Sensitive-data and volume controls

The logger must never include:

- LLM, Tavily, or OpenAlex API keys;
- authorization headers;
- environment-variable values;
- full prompts or complete message histories;
- raw model responses;
- raw Tavily results or extracted page bodies;
- stack traces for expected provider/job failures at `INFO` level.

Professor summaries, publication metadata, and public source URLs are intentionally visible because the user explicitly requested the extracted record. Each event stays on one terminal line. Existing graph budgets continue to bound the number of LLM log events.

## 6. Logging configuration

`python -m lab_tracker` configures the `lab_tracker` logger once with an `INFO`-level stream handler. The configuration avoids duplicate handlers and does not change Uvicorn access logging.

Tests may capture the named logger directly without starting Uvicorn. Importing application modules must not configure global logging or add handlers as a side effect.

## 7. Error handling

Logging failures must not change research outcomes. JSON serialization uses known Pydantic models and safe string fallbacks. Model exceptions are logged and then re-raised unchanged so the existing job error mapping remains authoritative.

The feature does not persist diagnostic events. Service restart clears in-memory jobs as before, while terminal history remains subject to the terminal application's own retention.

## 8. Verification

Automated tests will verify:

- an agent invocation emits start and completion events;
- a finalizer invocation emits start and completion events;
- an exception emits a failure event and is still propagated through existing graph behavior;
- a validated professor emits the requested structured fields;
- secrets, prompts, raw model output, and raw page content are absent;
- logging does not alter persistence or job status semantics.

A controlled live smoke test may be run only with the user's configured provider keys. It should perform the smallest useful single-professor check, confirm terminal events, and avoid printing secret values. Live calls are not part of the default offline test suite.

## 9. Non-goals

- Persistent log files or log rotation.
- A log viewer in the web interface.
- Full LangChain tracing or LangSmith integration.
- HTTP request/response logging for external providers.
- Database schema or REST API changes.
