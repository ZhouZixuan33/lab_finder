# Lab Application Tracker — Developer Guide

This guide covers the application architecture, local development workflow, research pipeline, database, diagnostics, testing, and REST API. For the shortest installation and usage instructions, see the [user guide](README.md).

## Architecture

Lab Application Tracker is a local, single-user full-stack application:

- `frontend/`: React, React Router, Vite, and JavaScript.
- `backend/`: FastAPI, Pydantic, and Python 3.12+.
- `backend/lab_tracker/services/`: faculty discovery, LangGraph orchestration, provider clients, validation, update jobs, and business services.
- `backend/lab_tracker/repositories/`: parameterized raw SQL grouped by domain.
- `backend/lab_tracker/db/`: SQLite connection factory and numbered SQL migrations.
- `backend/tests/` and `frontend/src/**/*.test.*`: automated backend and frontend tests.

During development, Vite serves the frontend on port `5173` and proxies `/api` to FastAPI on port `8000`. For a production-style local run, FastAPI serves the built frontend and API from port `8000`.

## Persistence and database schema

The backend uses the Python standard-library `sqlite3` module, parameterized raw SQL, explicit transactions, and numbered migrations. It does not use an ORM. The initial schema is defined in `backend/lab_tracker/db/migrations/001_initial.sql` and contains exactly four tables:

- `professors`: canonical identity, links, research summary, generated tags, source metadata, and timestamps.
- `application_status`: optional one-to-one application state, application date, and notes for a professor.
- `publications`: verified recent publications associated with a professor.
- `update_proposals`: current and proposed snapshots for a single-professor update check, with `pending`, `applied`, or `rejected` status.

The connection factory provides consistent SQLite configuration, including foreign-key enforcement and row handling. Migrations run automatically at application startup, so every entry point initializes the same schema before repositories execute SQL.

When changing the schema, add the next numbered `.sql` file instead of modifying a migration that may already have run. Keep SQL in repositories or migrations, use bound parameters for values, and wrap related writes in an explicit transaction.

## Prerequisites

- Python 3.12 or newer.
- Node.js 20 or newer, including npm.
- Google Chrome for Playwright end-to-end tests.
- An API key for an OpenAI-compatible chat model.
- Tavily and OpenAlex API keys.

As of August 2026, Tavily documents a free Researcher allocation of 1,000 credits per month, while OpenAlex documents a free API key with $1 of usage per day. Provider terms can change; consult the [Tavily API credit documentation](https://docs.tavily.com/documentation/api-credits) and [OpenAlex authentication and pricing documentation](https://developers.openalex.org/api-reference/authentication). The selected LLM provider may charge separately.

## Development setup

Clone the repository and install both runtime and development dependencies from PowerShell:

```powershell
git clone git@github.com:ZhouZixuan33/lab_application_tracker.git
cd lab_application_tracker
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
npm --prefix frontend install
Copy-Item .env.example .env
```

Edit `.env` and replace the placeholder credentials:

```dotenv
DATABASE_PATH=./data/lab_tracker.db
LLM_BASE_URL=
LLM_API_KEY=replace-me
LLM_MODEL=replace-me
TAVILY_API_KEY=replace-me
OPENALEX_API_KEY=replace-me
TAVILY_MIN_INTERVAL_SECONDS=1.0
OPENALEX_MIN_INTERVAL_SECONDS=1.0
WEB_HOST_MIN_INTERVAL_SECONDS=1.0
```

`LLM_BASE_URL` is optional. Leave it blank for the default OpenAI endpoint or set the base URL of an OpenAI-compatible provider. The provider interval settings have a validated minimum of one second. Never commit `.env`, API keys, or the SQLite database.

## Development workflow

Start FastAPI from the repository root:

```powershell
.venv\Scripts\python.exe -m lab_tracker
```

In a second terminal, start Vite:

```powershell
npm --prefix frontend run dev
```

Open `http://127.0.0.1:5173`. The API and interactive OpenAPI documentation remain available at `http://127.0.0.1:8000` and `http://127.0.0.1:8000/docs`.

The backend deliberately runs with one worker because active update jobs exist only in process memory. Restarting it makes old job IDs return `404`; professor, application, publication, and proposal records remain in SQLite.

## Research and update pipeline

Faculty discovery first parses the official UIUC ECE directory with deterministic code to obtain each professor's name, title, email, and official profile URL. Existing professors are identified before external research begins.

For each new professor, a bounded LangGraph `StateGraph` gives the model the verified name and email and exposes three protected tools:

- `search_professor_web`: search with Tavily for official profiles and research evidence.
- `extract_candidate_page`: fetch and extract text only from a server-registered candidate URL.
- `get_recent_publications`: query OpenAlex using the professor's validated identity.

The graph disables parallel tool calls and enforces budgets of at most three searches, five unique page extractions, one OpenAlex request, and eight agent turns. A separate structured-output model call creates the final professor record. Deterministic validation checks identities, evidence, URLs, publications, and tags before storage.

Generated tags are limited to one through three values from a controlled set of 12 broad ECE research categories. Narrow or invented tags fail validation rather than being stored.

After research, a separate `HomepageGraph` finds the professor's personal website. Its three nodes are `agent`, `tools`, and `finalize`. The prompt asks the model to read the official profile first, then search if needed. The model receives `search_web(query)` (Tavily Search) and `read_webpage(url)` (Tavily Extract, basic Markdown). Both providers share `TAVILY_API_KEY` and the Tavily rate limiter. There are at most five tool attempts, including failures, followed by one structured finalization without external tools. The fifth tool result goes directly to finalization. This means at most six model calls for this separate homepage stage.

The selected URL must appear in a successful page-read result and must not be the supplied official profile or its returned alias. Identity and page type are judged by the model. A confirmed URL is stored in the existing `lab_url` field and displayed as **Personal website**; `homepage_url` keeps its existing behavior. Unconfirmed results are null. Existing lab links are not automatically replaced: use a single-professor check and review its proposal. Tests use fake providers; real website extraction and model quality remain provider-dependent.

New-professor research runs serially. Provider-specific rate limiters enforce conservative request intervals, and every successfully validated professor is committed in an independent transaction. A later professor failure therefore does not discard earlier results. The operation only inserts professors absent from the database and never modifies existing records.

A single-professor check researches fresh data and creates an `update_proposals` row only when a real difference exists. The professor record changes only after the user applies the entire pending proposal. A proposal that fails to apply remains `pending`; a user may instead reject it permanently. A professor with a pending proposal cannot start another check.

An OpenAlex author-not-found result no longer aborts research. It emits `openalex.author_not_found`, skips further author lookups within that research run, and allows homepage discovery to continue. An internal `publications_unavailable` flag makes the update proposal retain existing publications rather than proposing their deletion. A successful empty publication result still uses normal comparison; other provider errors retain their existing handling.

Only one update job can be active at a time. Job IDs are UUID strings stored in memory, while proposal IDs are SQLite integer primary keys. The UI polls job state and shows compact running and completion feedback.

## Diagnostics

The backend writes structured research diagnostics to the terminal where `python -m lab_tracker` is running:

- `llm_call.started`: application code reached a real model invocation.
- `llm_call.completed`: the provider returned a response.
- `llm_call.failed`: authentication, quota, transport, model, or other invocation failure.
- `professor.extracted`: validated professor data is ready for persistence.

One professor may emit multiple LLM events because tool selection can take several turns and the finalizer is a separate model call. Successful extraction prints a one-line JSON summary of the validated identity, summary, tags, links, publications, sources, and confidence.

Diagnostics must remain secret-safe. API keys, authorization headers, prompts, raw model output, and extracted page bodies are not logged.

## Production-style local run

Build the frontend, then start the single-worker Python service:

```powershell
npm --prefix frontend run build
.venv\Scripts\python.exe -m lab_tracker
```

Open `http://127.0.0.1:8000`. FastAPI serves the Vite build, preserves `/api` route priority, and falls back to `index.html` for React routes. The default database is `data/lab_tracker.db`, and migrations run automatically on startup.

## Tests and quality checks

Run the backend tests and lint checks:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -p no:cacheprovider
.venv\Scripts\ruff.exe check backend/lab_tracker backend/tests
```

Run the frontend unit tests and production build:

```powershell
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Run the Playwright end-to-end suite with Google Chrome installed:

```powershell
npm --prefix frontend run test:e2e
```

Default automated tests use fakes or intercepted HTTP requests and do not spend LLM, Tavily, or OpenAlex quota.

## REST API

| Method and path | Purpose |
| --- | --- |
| `GET /api/health` | Check API and database availability. |
| `GET /api/professors` | Search, filter, sort, and paginate professors. |
| `GET /api/professors/{professor_id}` | Read a professor, publications, application, and pending proposal ID. |
| `GET /api/tags` | List generated tags and professor counts. |
| `PUT /api/professors/{professor_id}/application` | Create or replace the personal application record. |
| `DELETE /api/professors/{professor_id}/application` | Stop tracking the application. |
| `POST /api/update-checks` | Start new-professor discovery or a single-professor check. |
| `GET /api/update-checks/{job_id}` | Poll an in-memory job. |
| `GET /api/update-proposals` | List proposals by status and/or professor. |
| `GET /api/update-proposals/{proposal_id}` | Read current/proposed values and publication differences. |
| `POST /api/update-proposals/{proposal_id}/apply` | Atomically apply an entire pending proposal. |
| `POST /api/update-proposals/{proposal_id}/reject` | Permanently reject a pending proposal. |

Request and response schemas can be explored through the interactive OpenAPI page at `http://127.0.0.1:8000/docs` while the backend is running.

## Updating dependencies

Python dependency constraints live in `backend/pyproject.toml`. Update the relevant constraint, reinstall the editable package, and run the backend tests and Ruff before committing.

Frontend dependencies live in `frontend/package.json`, with exact resolved versions in `frontend/package-lock.json`. Use npm for all frontend dependency work so the lockfile remains authoritative:

```powershell
npm --prefix frontend outdated
npm --prefix frontend update
```

For an intentional major upgrade, install the selected package version explicitly. Commit `package.json` and `package-lock.json` together, then run frontend unit tests, the production build, and the end-to-end suite.

## Brand asset

The header uses the official orange-and-blue Block I published by the [University of Illinois Brand Guidelines](https://brand.illinois.edu/visual-identity/logo). The logo is displayed on a white field to retain the approved primary color treatment.
