# npm Package Manager Migration Implementation Plan

## Goal

Replace pnpm with npm as the frontend's only package manager, commit an npm lock file,
and prove that installation, unit tests, the production build, and Playwright E2E tests
continue to work without changing application behavior.

## Scope and invariants

- Preserve all dependency declarations and scripts in `frontend/package.json`.
- Do not intentionally upgrade application or tooling dependencies.
- Keep exactly one frontend lock file: `frontend/package-lock.json`.
- Do not change backend code, REST APIs, SQLite, `.env`, or application data.
- Preserve unrelated user workspace changes and do not stage them.
- Do not use npm resolver bypasses such as `--force` or `--legacy-peer-deps`.

## Task 1: Preflight and protect the cleanup boundary

Before deleting generated dependencies:

1. Record `node --version` and `npm --version`.
2. Confirm `frontend/package.json` and `frontend/pnpm-lock.yaml` exist.
3. Confirm `frontend/package-lock.json` does not yet exist.
4. Resolve the absolute `frontend/node_modules` path.
5. Verify that the resolved path is exactly the `node_modules` child of the resolved
   repository `frontend` directory.
6. Recheck `git status --short` so unrelated changes are known and preserved.

Only the verified `frontend/node_modules` directory may be recursively removed. It is
ignored generated data and will be recreated by npm. No computed, unresolved, wildcard,
home-directory, repository-root, or parent-directory deletion is allowed.

## Task 2: Replace active pnpm commands

Use `apply_patch` to update `frontend/playwright.config.js`:

```text
pnpm dev --host 127.0.0.1 --port 4173
```

becomes:

```text
npm run dev -- --host 127.0.0.1 --port 4173
```

Use `apply_patch` to update active instructions in `README.md`:

- prerequisite: Node.js 20+ with npm;
- install: `npm --prefix frontend install`;
- development: `npm --prefix frontend run dev`;
- build: `npm --prefix frontend run build`;
- unit tests: `npm --prefix frontend test -- --run`;
- E2E tests: `npm --prefix frontend run test:e2e`.

Do not rewrite historical design/implementation documents solely because they mention
commands used during earlier development.

## Task 3: Generate the npm dependency tree and lock file

After the cleanup boundary has been verified:

1. Remove the existing generated `frontend/node_modules` directory.
2. Remove the tracked generated `frontend/pnpm-lock.yaml` file.
3. Run from the repository root:

   ```powershell
   npm --prefix frontend install
   ```

4. Confirm npm recreated `frontend/node_modules` and generated
   `frontend/package-lock.json`.
5. Confirm `frontend/package.json` did not change unexpectedly.

The install requires registry network access. If dependency resolution fails, stop and
report the original npm error. Do not change versions or add resolver flags. If npm
reports audit findings but installation succeeds, record them for the handoff and do not
run `npm audit fix`, because that can change dependency versions outside this migration.

## Task 4: Validate with npm only

Run in order:

```powershell
npm --prefix frontend test -- --run
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Expected outcomes:

- all existing Vitest tests pass;
- Vite produces `frontend/dist` successfully;
- Playwright starts Vite through the new npm command and all E2E tests pass;
- no command depends on pnpm being installed.

If Chrome is unavailable for Playwright, distinguish that environment prerequisite from
an npm migration defect. Do not silently replace the configured browser.

## Task 5: Repository consistency review

Verify:

- `frontend/package-lock.json` is present;
- `frontend/pnpm-lock.yaml` is absent;
- `frontend/package.json` contains the same dependency and script declarations as before;
- active `README.md`, `frontend/package.json`, and executable frontend configuration
  contain no pnpm command;
- `git diff --check` passes;
- only the lock-file replacement, README, Playwright configuration, design, and plan
  files are candidates for migration commits;
- `.env.example`, `docs/superpowers/specs/a.md`, `tmp/`, and other unrelated workspace
  changes remain untouched and unstaged.

## Task 6: Commit and handoff

Commit the implementation as:

```text
build: migrate frontend package manager to npm
```

The commit includes:

- removal of `frontend/pnpm-lock.yaml`;
- addition of `frontend/package-lock.json`;
- npm-based Playwright web-server command;
- npm-based README instructions.

Do not push automatically. Report test results, npm audit output if any, the commit hash,
and the new clone/install command to the user.
