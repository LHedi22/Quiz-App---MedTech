# Phase 10 — Deployment

## Objective
Ship the backend to Cloud Run, configure production Supabase, and prepare both Flutter
clients for release/distribution.

## Subtask 10.1 — Backend deployment
**Steps:**
- Dockerize the FastAPI backend.
- Deploy to Google Cloud Run with production environment variables (Section 8 of
  CLAUDE.md) set via Cloud Run's secret manager, not hardcoded.
- Confirm autoscaling and a health check are configured.

**Definition of Done:**
- [ ] `GET /health` on the deployed Cloud Run URL returns 200 from an external client (not
      localhost).
- [ ] A full Phase 9-style E2E smoke test passes against the deployed production-like
      environment.

## Subtask 10.2 — Production Supabase setup
**Steps:**
- Apply all Phase 1 migrations to the production Supabase project.
- Re-verify RLS policies against production (repeat the cross-user test from Subtask 1.2
  against the real prod project, using disposable test accounts).

**Definition of Done:**
- [ ] Migrations applied cleanly with zero manual intervention needed, verified by running
      the migration script against a fresh prod-equivalent instance.
- [ ] Cross-user RLS test passes against production.

## Subtask 10.3 — Client release prep
**Steps:**
- Configure web app build for static hosting (Firebase Hosting, Cloud Storage + CDN, or
  equivalent) pointed at the production backend URL.
- Configure mobile app build settings (app icons, bundle IDs, signing config placeholders)
  for eventual store submission — actual store submission is out of scope unless
  explicitly requested later.

**Definition of Done:**
- [ ] Web app production build loads and successfully authenticates against production
      Supabase + backend, verified manually and noted in PROGRESS.md.
- [ ] Mobile app builds a release APK/IPA without errors, pointed at production backend.

## Phase 10 Definition of Done
- [ ] All subtask DoD boxes checked.
- [ ] PROGRESS.md updated, code committed.
- [ ] A final PROGRESS.md summary entry states the project has completed all 11 phases.

## Next
There is no next file. Do a final pass: re-read CLAUDE.md Section 2 (non-negotiable
rules) and confirm nothing in the shipped system violates any of them, especially the
no-LLM rule. Log the confirmation in PROGRESS.md.