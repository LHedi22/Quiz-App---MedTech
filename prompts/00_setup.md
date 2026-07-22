# Phase 0 — Repo scaffolding, tooling, CI skeleton

## Objective
Stand up the repo structure exactly as described in CLAUDE.md Section 5, with working
tooling, so every later phase can build on a consistent foundation.

## Subtask 0.1 — Repo structure
**Steps:**
- Create `/backend`, `/web`, `/mobile`, `/prompts`, `/docs` directories.
- Initialize `backend` as a Python project (`pyproject.toml` or `requirements.txt`),
  FastAPI + uvicorn + pytest + black + ruff as dependencies.
- Initialize `web` and `mobile` as Flutter projects (`flutter create`).
- Create `/docs/PROGRESS.md` and `/docs/BLOCKERS.md` (empty, with a one-line header each).
- Add root `.gitignore` covering Python, Flutter/Dart, and OS artifacts.

**Definition of Done:**
- [ ] `backend`, `web`, `mobile` each run their respective "hello world" (uvicorn boots,
      `flutter run` shows default screen) without errors.
- [ ] `pytest` runs (even with zero tests) with exit code 0 in `/backend`.
- [ ] `git status` is clean after an initial commit.

## Subtask 0.2 — Backend skeleton
**Steps:**
- Create `app/main.py` with a FastAPI app and a `/health` endpoint returning `{"status": "ok"}`.
- Create empty `app/routers/`, `app/services/`, `app/models/`, `app/ml/` packages.
- Add `black` and `ruff` configs, and a `Makefile` or `justfile` with `lint`, `format`,
  `test` targets.

**Definition of Done:**
- [ ] `GET /health` returns 200 with the expected body via a pytest test.
- [ ] `make lint` and `make format` run without errors on the current codebase.

## Subtask 0.3 — CI skeleton
**Steps:**
- Add a GitHub Actions workflow (or equivalent) that runs backend lint + tests on push.
- Add a second job that runs `flutter analyze` + `flutter test` for both `web` and `mobile`.

**Definition of Done:**
- [ ] CI config file is valid YAML and references real commands that succeed locally.
- [ ] A trivial passing test exists in each of backend/web/mobile so CI has something to run green.

## Phase 0 Definition of Done
- [ ] All three subtasks' DoD boxes are checked.
- [ ] `/docs/PROGRESS.md` has one entry per subtask.
- [ ] Repo is committed with conventional commit messages, one per subtask.

## Next
Open `01_database_schema.md` and continue the loop.