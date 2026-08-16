# Lab Application Tracker

A local, single-user full-stack application for researching UIUC ECE professors and tracking lab applications. It discovers faculty from the official directory, uses a bounded LangGraph research workflow to verify lab links, summarize research, classify each professor into one to three controlled broad research categories, and collect recent publications, then stores the results in SQLite.

## Features

- Responsive professor catalog with search, broad-category filtering, application-state filtering, and pagination.
- Professor details with research summary, homepage/lab links, evidence sources, recent OpenAlex publications, and last-check time.
- Simple application flow: `Interested → Applied → Accepted/Rejected`, with one optional application date and notes.
- “Find new professors” only inserts faculty absent from the database. Existing professor records are never changed by this operation.
- Per-professor checks create a pending difference proposal. Nothing changes until the user applies the whole proposal; rejecting it is final.
- In-memory UUID update jobs with compact UI feedback and session-based polling recovery.

## Architecture

- Frontend: React, React Router, Vite, JavaScript.
- Backend: FastAPI, Pydantic, Python 3.12+.
- Research: LangChain `ChatOpenAI` wrapped in an explicit LangGraph `StateGraph`, with Tavily search, bounded page extraction, and identity-bound OpenAlex queries.
- Persistence: standard-library `sqlite3`, parameterized raw SQL, numbered migrations, and explicit transactions. No ORM and no MCP server are used.

The SQLite schema contains exactly four tables:

- `professors`: canonical professor identity and researched profile.
- `application_status`: optional one-to-one personal application record.
- `publications`: verified recent publications for each professor.
- `update_proposals`: immutable current/proposed snapshots for single-professor confirmation.

## Prerequisites

- Python 3.12 or newer.
- Node.js 20 or newer and pnpm.
- Google Chrome for the Playwright end-to-end suite.
- An API key for an OpenAI-compatible chat model.
- Tavily and OpenAlex API keys.

As of August 2026, Tavily documents a free Researcher allocation of 1,000 credits per month, while OpenAlex documents a free API key with $1 of usage per day. Provider terms and quotas can change; check the [Tavily pricing documentation](https://docs.tavily.com/documentation/api-credits) and [OpenAlex authentication and pricing documentation](https://developers.openalex.org/api-reference/authentication) before running a large discovery. The LLM provider may charge separately.

The app processes new professors serially and applies conservative provider intervals, but one professor can still consume multiple search/model calls. Successful professors are committed independently, so a later failure does not discard earlier API work.

## Installation

From the repository root in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
pnpm --dir frontend install
Copy-Item .env.example .env
```

Set the following values in `.env`:

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

`LLM_BASE_URL` is optional. Leave it blank for the default OpenAI endpoint, or set an OpenAI-compatible endpoint. Never commit `.env` or the SQLite database.

## Development

Start the API from the repository root:

```powershell
.venv\Scripts\python.exe -m lab_tracker
```

In a second terminal, start Vite:

```powershell
pnpm --dir frontend dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to `http://127.0.0.1:8000`.

## Research diagnostics

When the backend is started with `python -m lab_tracker`, safe research diagnostics are printed to the same terminal. LLM activity is shown by these events:

- `llm_call.started`: application code reached a real model invocation;
- `llm_call.completed`: the provider returned a response;
- `llm_call.failed`: the invocation raised an authentication, quota, transport, or model error.

Successful validation also emits `professor.extracted` followed by a one-line JSON object containing the professor identity, summary, tags, links, publications, sources, and confidence. API keys, authorization headers, prompts, raw model output, and extracted page bodies are never logged.

Each professor can produce several LLM events because the bounded research agent may call tools over multiple turns and then use a separate structured finalizer.

LLM-generated tags are restricted to one through three values from a controlled set of
12 broad ECE research categories. The finalizer receives the complete taxonomy in its
system prompt, and deterministic validation rejects narrow or invented categories
instead of silently storing them.

## Production-style local run

Build the frontend, then start the one-worker Python service:

```powershell
pnpm --dir frontend build
.venv\Scripts\python.exe -m lab_tracker
```

Open `http://127.0.0.1:8000`. FastAPI serves the Vite build and falls back to `index.html` for React routes while preserving `/api` priority.

The application intentionally runs with one worker because active jobs live only in process memory. Restarting the backend makes old job IDs return 404; persisted professor, application, publication, and proposal data remain in SQLite. The default database is `data/lab_tracker.db`, and migrations run automatically at startup.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -p no:cacheprovider
.venv\Scripts\ruff.exe check backend/lab_tracker backend/tests
pnpm --dir frontend test -- --run
pnpm --dir frontend build
pnpm --dir frontend test:e2e
```

All default tests use fakes or intercepted HTTP requests and do not spend LLM, Tavily, or OpenAlex quota.

## REST API

| Method and path | Purpose |
| --- | --- |
| `GET /api/health` | Check API and database availability. |
| `GET /api/professors` | Search, filter, sort, and paginate professors. |
| `GET /api/professors/{professor_id}` | Read a professor, publications, application, and pending proposal ID. |
| `GET /api/tags` | List generated tags and professor counts. |
| `PUT /api/professors/{professor_id}/application` | Create or replace the personal application record. |
| `DELETE /api/professors/{professor_id}/application` | Stop tracking the application. |
| `POST /api/update-checks` | Start either new-professor discovery or a single-professor check. |
| `GET /api/update-checks/{job_id}` | Poll an in-memory job. |
| `GET /api/update-proposals` | List proposals by status and/or professor. |
| `GET /api/update-proposals/{proposal_id}` | Read current/proposed values and publication differences. |
| `POST /api/update-proposals/{proposal_id}/apply` | Atomically apply the entire pending proposal. |
| `POST /api/update-proposals/{proposal_id}/reject` | Permanently reject the pending proposal. |

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs` while the backend is running.

## Brand asset

The header uses the official orange-and-blue Block I published by the [University of Illinois Brand Guidelines](https://brand.illinois.edu/visual-identity/logo). The logo is displayed on a white field to retain the approved primary color treatment.
