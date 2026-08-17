# npm Package Manager Migration Design

**Date:** 2026-08-17  
**Status:** Approved design, pending implementation

## 1. Objective

Replace pnpm with npm as the frontend's only package manager so a beginner can clone
the repository and use the npm installation included with Node.js. Preserve the current
frontend dependency versions, scripts, application behavior, and backend architecture.

## 2. Source of truth

After migration, the frontend has exactly one dependency lock file:

```text
frontend/package-lock.json
```

`frontend/pnpm-lock.yaml` will be removed. The repository will not maintain npm and pnpm
lock files together because separate resolvers could produce different dependency trees.

`frontend/package.json` remains the dependency and script manifest. The migration does
not intentionally upgrade React, React Router, Vite, Vitest, Playwright, or testing
libraries. The new lock file must be generated from the existing manifest with npm.

## 3. Installation workflow

The existing pnpm-generated `frontend/node_modules` directory is generated data. During
implementation it will be removed only after its resolved path is verified as the
project's `frontend/node_modules`, then recreated with npm:

```powershell
npm --prefix frontend install
```

No backend virtual environment, SQLite database, `.env`, source file, or user-authored
untracked content is removed by this cleanup.

## 4. Command mapping

Repository instructions will use these commands:

| Operation | npm command |
| --- | --- |
| Install | `npm --prefix frontend install` |
| Development server | `npm --prefix frontend run dev` |
| Unit tests | `npm --prefix frontend test -- --run` |
| Production build | `npm --prefix frontend run build` |
| End-to-end tests | `npm --prefix frontend run test:e2e` |

The Playwright web-server command runs inside `frontend` and will change from pnpm to:

```text
npm run dev -- --host 127.0.0.1 --port 4173
```

The extra `--` is required to pass the host and port arguments through npm to Vite.

## 5. Documentation changes

`README.md` will:

- replace the pnpm prerequisite with npm, noting that npm is installed with Node.js;
- replace installation, development, build, unit-test, and E2E commands with the npm
  equivalents;
- retain the existing Python, API-key, production-run, and database instructions.

Historical design and implementation documents will not be rewritten merely because
they describe past commands. Active user-facing instructions and executable
configuration must contain no pnpm command.

## 6. Runtime and data impact

This is a frontend tooling migration only. It does not change:

- React components or browser behavior;
- frontend API requests;
- FastAPI, LangGraph, raw SQL, or SQLite;
- REST API paths or payloads;
- `.env` variables or external provider configuration;
- existing professor, publication, proposal, or application data.

The production build remains `frontend/dist`, and FastAPI continues serving that build
in production-style local runs.

## 7. Error handling

- If npm cannot resolve the existing manifest, stop without editing dependency versions
  automatically and report the resolver error.
- If installation or validation fails, do not commit a partial lock-file migration.
- Do not use `--force`, `--legacy-peer-deps`, or lock-file suppression to hide dependency
  conflicts.
- The ignored `frontend/node_modules` directory can be regenerated and is not committed.

## 8. Verification

Run the following from the repository root:

```powershell
npm --prefix frontend install
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Then verify:

- `frontend/package-lock.json` exists and is tracked;
- `frontend/pnpm-lock.yaml` is removed;
- frontend unit tests pass;
- the production build succeeds;
- all Playwright E2E tests pass using npm to launch Vite;
- active README and executable configuration contain no pnpm commands;
- unrelated user workspace changes remain untouched and unstaged.

## 9. Commit boundary

The lock-file replacement, Playwright command, README updates, and associated validation
belong in one migration commit because leaving either lock file or executable commands
half-migrated would make the repository inconsistent.
