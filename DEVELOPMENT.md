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

New-professor research and single-professor refreshes use the same enforced sequence: personal homepage discovery, website-based summary and category validation, then OpenAlex publication retrieval. Network and model calls run outside database write transactions.

`UnifiedResearchGraph` is the production entry point for both new and refresh runs. Its nodes are `homepage_agent`, `homepage_tools`, `prepare_research`, `research_agent`, `research_tools`, `finish_collection`, `finalizer`, `validate_schema`, and `incomplete`.

- Homepage Agent keeps the existing discovery prompt: read the official profile first, follow a personal-site link when present, otherwise search; read the selected target and confirm identity. Its tools are `search_web(query)` and `read_webpage(url)`. The agent returns the URL or null directly without another homepage finalizer call. As before, unread/invalid/official-profile URLs are rejected to null. Model/provider execution errors propagate.
- `prepare_research` clears homepage messages and passes only the fixed identity and confirmed URL to the research model. There is no page cache, source-ID registry or publication state.
- Research Agent uses `read_webpage(url)` and `map_website(url, instructions)`; it independently chooses which of the supplied official/personal pages and related pages to read. It has no Search tool. Source relevance is a model decision, not a code audit.
- Read uses Tavily Extract advanced Markdown. Each response is capped at 12,000 characters before entering messages, with a separate local truncation flag and original length. Re-reading a URL makes another request. Map returns at most 20 URLs, not webpage evidence.
- All three Tavily operations share a maximum of ten requests per professor, including failed requests. Budget is reserved before provider dispatch; cancellation while awaiting a limiter may conservatively consume a slot without a completed HTTP request. Production Search uses direct HTTP without SDK retries. No allowance is sent to the model. After the tenth response, collection ends without another agent call.
- Collection has a 120-second deadline across both stages and an 80-step graph fallback. External cancellation propagates. Deadline/step exhaustion can finalize completed research evidence; no research evidence means incomplete. There are no retained historical checkpoints.
- Finalizer returns `success` or `insufficient_evidence` with a reason. `validate_schema` checks structure, paired invitation fields and 1–3 distinct exact taxonomy tags only. It does not match invitation quotes or audit citation URLs. There is at most one correction (two generations total), each with a 30-second timeout. No evidence means no generation; insufficient evidence means no publications or persistence.

Only after graph success does the outer backend call OpenAlex, with a 30-second timeout, and attach normalized publications without changing research text. The existing author matching, publication window and provider memory cache remain unchanged. Publication failures retain the completed research and mark publications unavailable, preserving existing papers in refresh proposals; cancellation still propagates.

Profile fields use the same names in the database, API, graph and UI: `official_profile_url` is the UIUC faculty profile; `personal_homepage_url` is the confirmed personal site. Migration 003 converts the old directory/homepage/lab columns and all proposal snapshots. It rejects conflicting personal URLs before changing the schema and makes an online SQLite backup next to each existing database before migration. A valid legacy `lab_url` wins; otherwise a non-official `homepage_url` is used. No old field remains in the current API.

New-professor research runs serially. Provider-specific rate limiters enforce conservative request intervals, and every successfully validated professor is committed in an independent transaction. A later professor failure therefore does not discard earlier results. The operation only inserts professors absent from the database and never modifies existing records.

A single-professor check researches fresh data and creates an `update_proposals` row only when a real difference exists. The professor record changes only after the user applies the entire pending proposal. A proposal that fails to apply remains `pending`; a user may instead reject it permanently. A professor with a pending proposal cannot start another check.

An OpenAlex author-not-found result does not abort research. It emits `openalex.author_not_found` and returns the already completed website summary with an internal `publications_unavailable` flag. That flag makes the update proposal retain existing publications rather than proposing their deletion. A successful empty publication result still uses normal comparison. Other publication provider failures follow the same unavailable behavior; research/model failures still abort before persistence.

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
