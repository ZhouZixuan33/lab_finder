# User and Developer Documentation Split Implementation Plan

## Goal

Turn `README.md` into a concise English user guide for cloning and running the app, and
create a root-level `DEVELOPMENT.md` containing the project's technical, testing, API,
and maintenance documentation.

## Scope and invariants

- Documentation-only change: no application, configuration, dependency, API, or schema
  behavior changes.
- Preserve all currently correct technical information by moving it to the appropriate
  guide or deliberately omitting it according to the approved design.
- Keep all setup commands aligned with the npm-based frontend workflow.
- Never include real API keys, `.env` contents, SQLite data, or local machine secrets.
- Preserve unrelated workspace changes, especially the existing `.env.example` deletion,
  `docs/superpowers/specs/a.md`, and `tmp/`; do not stage them.

## Task 1: Build a content migration map

Read the current `README.md` and classify every section before editing:

| Current content | Destination |
| --- | --- |
| Project purpose and features | `README.md` |
| User prerequisites and configuration | `README.md`, shortened |
| Architecture and four-table description | `DEVELOPMENT.md` |
| Provider pricing and job rate-limit behavior | `DEVELOPMENT.md` |
| Two-terminal development workflow | `DEVELOPMENT.md` |
| Research diagnostics and controlled tags | `DEVELOPMENT.md` |
| Production serving internals | `DEVELOPMENT.md` |
| Test commands | `DEVELOPMENT.md` |
| REST API table | `DEVELOPMENT.md` |
| Brand attribution | `DEVELOPMENT.md` |

Before writing, verify the exact current clone URL, npm commands, backend entry point,
ports, database path, REST endpoints, diagnostics names, and table names against tracked
repository files.

## Task 2: Create the developer guide

Use `apply_patch` to add root-level `DEVELOPMENT.md` with:

1. title, scope, and link back to `README.md`;
2. architecture and component responsibilities;
3. SQLite tables and raw-SQL persistence rules;
4. full developer setup with `backend[dev]` and npm;
5. two-terminal FastAPI/Vite workflow on ports 8000 and 5173;
6. LangGraph, Tavily, OpenAlex, controlled tag taxonomy, and job behavior;
7. diagnostic event definitions and secret-safe logging rules;
8. production-style frontend build and FastAPI SPA serving;
9. backend, frontend, build, and Playwright validation commands;
10. complete REST API table and OpenAPI URL;
11. dependency-update workflow;
12. UIUC brand asset attribution.

Reuse accurate prose from the current README where practical, but organize it for a
developer reading path rather than copy the old document wholesale. Keep external links
that support provider quotas and UIUC brand attribution.

## Task 3: Rewrite the user README

Use `apply_patch` to replace `README.md` with a concise English guide containing:

1. title and one-paragraph purpose;
2. six or fewer feature bullets;
3. short Windows requirements;
4. one primary Quick Start command sequence;
5. one `.env` template with placeholders;
6. first-launch instructions;
7. local data and migration note;
8. one troubleshooting sentence;
9. a prominent link to `DEVELOPMENT.md`.

The happy path must be complete without requiring the developer guide:

```powershell
git clone git@github.com:ZhouZixuan33/lab_application_tracker.git
cd lab_application_tracker
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .\backend
npm --prefix frontend install
Copy-Item .env.example .env
notepad .env
npm --prefix frontend run build
.venv\Scripts\python.exe -m lab_tracker
```

Direct the user to `http://127.0.0.1:8000` after startup. Do not include test commands,
REST endpoint tables, architecture internals, detailed log events, or provider pricing
in the user README.

## Task 4: Verify facts and links

Perform focused, read-only checks:

- compare the REST API table with routers under `backend/lab_tracker/api`;
- confirm the four table names in the migration SQL;
- confirm frontend scripts in `frontend/package.json`;
- confirm Vite proxy and ports in `frontend/vite.config.js` and backend startup code;
- confirm `README.md` and `DEVELOPMENT.md` link to one another;
- confirm user install omits `[dev]` and developer install includes it;
- confirm all active package-manager commands use npm;
- confirm neither document contains actual credential values;
- run `git diff --check`.

Review the final README for brevity: each technical detail must either be required to
run the app or be moved to `DEVELOPMENT.md`. Review the developer guide for completeness:
every technical section removed from the old README must have a clear destination or an
explicit design reason for omission.

Application tests are not required for this documentation-only change. If fact-checking
reveals a mismatch between docs and executable configuration, update the documentation
to match the existing behavior; do not change runtime code within this task.

## Task 5: Commit and handoff

Stage only:

- `README.md`;
- `DEVELOPMENT.md`.

Commit as:

```text
docs: split user and developer guides
```

Report the final user README structure, the developer-guide coverage, the verification
performed, and the commit hash. Do not push automatically.
