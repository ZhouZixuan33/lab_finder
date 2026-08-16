# Research Diagnostic Logging Implementation Plan

## Goal

Print safe professor extraction data and authoritative LLM invocation events to the backend terminal without changing research, persistence, or API behavior.

## Task 1: Add a safe diagnostic logging boundary

Create `backend/lab_tracker/diagnostics.py` with:

- idempotent `INFO` stream-handler configuration for the `lab_tracker` logger;
- compact, one-line JSON event serialization;
- helpers for `professor.extracted` and `professor.research_failed`;
- field allowlists that exclude prompts, raw responses, page bodies, headers, and secrets.

Update `backend/lab_tracker/__main__.py` to configure logging before Uvicorn starts. Add focused unit tests for serialization, duplicate-handler prevention, and secret-safe failure output.

## Task 2: Instrument actual LLM invocation boundaries

Update `backend/lab_tracker/services/research_graph.py`:

- emit `llm_call.started` immediately before each agent and finalizer `ainvoke`;
- emit `llm_call.completed` with phase, attempt, duration, and agent tool-call count;
- emit `llm_call.failed` with phase, attempt, duration, and exception type, then re-raise unchanged;
- use `time.perf_counter()` for elapsed time.

Extend graph tests to prove success/failure events correspond to real fake-model invocations and that exception text is absent.

## Task 3: Print validated professor payloads

Update the new-professor orchestration and single-professor update service:

- emit `professor.extracted` only after validated research returns and before persistence/diffing;
- include the approved identity, summary, tag, publication, source, and confidence fields;
- emit `professor.research_failed` for candidate-level failures without partial results.

Extend offline job/update tests to verify the payload and unchanged persistence semantics.

## Task 4: Verify and document

- Run Ruff and the complete backend test suite.
- Restart the local backend so logging configuration is active.
- Run the smallest safe live check only if it can be bounded to one professor and the user has no pending proposal.
- Confirm terminal output contains LLM start/completion or failure evidence and never prints credential values.
- Add a short README diagnostics section.

No schema, REST API, frontend, or provider-budget changes are included.
