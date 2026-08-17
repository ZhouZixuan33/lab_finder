# User and Developer Documentation Split Design

**Date:** 2026-08-17  
**Status:** Approved design, pending implementation

## 1. Objective

Make the GitHub landing page easy for a first-time user to follow while preserving the
project's technical and maintenance documentation. `README.md` becomes an English user
guide; a new root-level `DEVELOPMENT.md` becomes the English developer guide.

The split is documentation-only. It does not change application code, dependencies,
configuration semantics, APIs, database schema, or runtime behavior.

## 2. Audience and file ownership

### `README.md`

Audience: a user who wants to clone the repository and run the application locally.

The README must answer only:

- What does the application do?
- What must be installed or obtained first?
- How is it installed and configured?
- How is it started?
- What should the user do on first launch?
- Where is local data stored?
- Where can a developer find technical documentation?

### `DEVELOPMENT.md`

Audience: a developer who wants to understand, modify, test, or extend the project.

The developer guide owns architecture, development topology, internal diagnostics,
database design, research orchestration, testing, API reference, and maintenance details.

Both files link to each other near their opening sections so readers can switch context
without searching the repository.

## 3. User README structure

`README.md` will remain the GitHub-rendered landing page and use this structure:

1. Project name and one-paragraph purpose
2. Features
3. Requirements
4. Quick Start
5. Configuration
6. First Use
7. Local Data
8. Development link

### 3.1 Requirements

Keep the user prerequisites concise:

- Windows PowerShell instructions;
- Python 3.12 or newer;
- Node.js 20 or newer with npm;
- LLM, Tavily, and OpenAlex API keys.

Google Chrome is not a user requirement because it is needed only for Playwright E2E
testing; it moves to `DEVELOPMENT.md`.

### 3.2 Quick Start

The primary happy path uses a production-style local run and one application process:

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

The user install intentionally omits the Python `[dev]` extra. Test and lint tools are
not required merely to run the application.

The README tells the user to edit `.env` after copying the example and before building
or starting the application. It presents one concise environment-variable template and
does not include provider pricing, research budgets, or diagnostic implementation detail.

After startup, the README directs the user to `http://127.0.0.1:8000`.

### 3.3 First use and local data

The first-use section explains that a new clone has an empty SQLite database and that
the user should select **Find New Professors** to populate it. It notes that research
uses external API quota without describing orchestration internals.

The local-data section states that `.env` and `data/lab_tracker.db` are not cloned or
committed. It briefly explains that migrating existing personal data requires copying
the SQLite file separately while the backend is stopped.

## 4. Developer guide structure

Create `DEVELOPMENT.md` at the repository root with:

1. Scope and link back to `README.md`
2. Architecture and component responsibilities
3. SQLite tables and persistence rules
4. Development setup with the Python `[dev]` extra
5. Split frontend/backend development workflow
6. Research pipeline and controlled tag taxonomy
7. Research diagnostics and logging events
8. Production-style serving behavior
9. Test, lint, build, and Playwright commands
10. Complete REST API table
11. Dependency-update workflow
12. Brand asset attribution

The developer setup uses:

```powershell
.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
```

and documents the two-terminal development mode on ports 8000 and 5173. The existing
technical facts in the README move to this file rather than being discarded.

## 5. Content removed from the user README

Move these sections out of `README.md`:

- detailed architecture and table responsibilities;
- provider pricing and quota discussion;
- serial job implementation detail;
- two-terminal frontend/backend development workflow;
- individual diagnostic event definitions;
- controlled-taxonomy implementation detail;
- production SPA fallback and in-memory job explanation;
- test and lint commands;
- complete REST API endpoint table;
- brand asset implementation detail.

The README may retain one final sentence linking to `DEVELOPMENT.md`; it must not copy
the moved content back into a second long technical appendix.

## 6. Error handling and troubleshooting boundary

The user README includes only one short troubleshooting note: startup failures should
first be checked against required `.env` values and the backend terminal output.

Developer-specific troubleshooting, test environment failures, provider diagnostics,
and job-lifecycle behavior belong in `DEVELOPMENT.md`. Neither guide exposes API keys,
real `.env` contents, database contents, or other secrets.

## 7. Verification

Documentation verification will confirm:

- `README.md` contains the complete user happy path and no required step is available
  only in the developer guide;
- `README.md` links to `DEVELOPMENT.md` and the reverse link exists;
- every referenced command matches the npm-based repository configuration;
- runtime user installation omits `[dev]`, while developer installation includes it;
- development ports, production port, API paths, database path, and log event names
  match the current codebase;
- all existing technical content is either retained in `DEVELOPMENT.md` or deliberately
  omitted according to this design;
- `git diff --check` passes;
- unrelated user workspace changes remain untouched and unstaged.

Because this change is documentation-only, application tests do not need to be rerun
unless implementation reveals an executable configuration inconsistency.

## 8. Commit boundary

The rewritten `README.md` and new `DEVELOPMENT.md` belong in one implementation commit:

```text
docs: split user and developer guides
```
