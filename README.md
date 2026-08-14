# Exam Version Generator & Scanner

A professor-only tool that solves exam cheating caused by manual quiz-version creation.

To prevent cheating, professors traditionally create multiple versions of the same
quiz by hand (shuffled question order, shuffled answer order per question), then
grade each version separately, tracking which shuffle maps to which original answer
key. This app automates that: upload one Excel sheet of MCQ questions, generate N
independently-shuffled printable versions with QR codes, scan completed answer
sheets with the mobile app, and get automatically graded results — with anything
ambiguous (unclear marks, unreadable QR, multiple marks) routed to a professor
review queue instead of silently guessed at.

## How it works

1. Professor uploads one Excel sheet: MCQ questions, options, and correct answers.
2. The backend generates N versions, each with independently shuffled question
   order and answer-option order.
3. Each version gets a printable PDF with a QR code encoding its version ID.
4. Professor prints, distributes, and administers the exam on paper.
5. Professor scans each completed sheet with the mobile app.
6. The backend decodes the QR code, looks up that version's shuffle mapping,
   detects filled bubbles, translates positions back to canonical questions, and
   scores against the master key.
7. Low-confidence detections (unclear marks, unreadable QR, multiple marks) are
   flagged for review on the web dashboard. Everything else finalizes automatically.

**No LLM is used anywhere in this system.** Every step — parsing, shuffling,
alignment, bubble detection, scoring — is deterministic logic or a small trained
classical ML model (scikit-learn). MCQ only; no other question types.

## Two clients, one backend

- **Web app** (`/web`) — the professor's control center: quiz creation, Excel
  upload, version generation, PDF download, results dashboard, flagged-answer
  review. Next.js 16 (App Router, TypeScript), Tailwind CSS.
- **Mobile app** (`/mobile`) — scanning only: camera-first batch scanning of a
  stack of papers, local queue with sync/retry, batch summary. Flutter.

Both clients talk to the same FastAPI backend (`/backend`), backed by Supabase
(Postgres, Auth, Storage).

## Tech stack

| Layer            | Choice                                                     |
|-------------------|--------------------------------------------------------------|
| Backend           | FastAPI (Python), deployable to Cloud Run                    |
| Database / Auth   | Supabase (Postgres + Auth + Storage)                          |
| Web client        | Next.js 16 (App Router, TypeScript), Tailwind CSS             |
| Mobile client      | Flutter (iOS + Android)                                        |
| Computer vision    | OpenCV (alignment, bubble region detection)                    |
| Bubble classifier  | scikit-learn (trained on labeled bubble crops)                 |
| QR generate/decode | `qrcode` / `pyzbar`                                             |
| PDF generation     | ReportLab                                                       |
| Excel parsing      | `openpyxl`                                                       |

## Repo structure

```
/backend      FastAPI app (routers, services, ML pipeline, migrations, tests)
/web          Next.js web app — professor dashboard
/mobile       Flutter mobile app — scanning only
/shared       Shared Dart package (mobile only)
/prompts      Phase-by-phase build prompts this project was built from
/docs         PROGRESS.md (build log) and BLOCKERS.md (open items)
```

## Running locally

Everything runs against a local Supabase stack (Docker) by default — no hosted
account needed for development.

```bash
# 1. Supabase (from /backend)
cd backend
supabase start
python migrations/apply_migrations.py   # DATABASE_URL defaults to the local stack

# 2. Backend API
uvicorn app.main:app --reload           # http://localhost:8000

# 3. Web app (in a separate terminal, from /web)
cd web
npm install
npm run dev                             # http://localhost:3000

# 4. Mobile app (in a separate terminal, from /mobile)
cd mobile
flutter run
```

`web/.env.local` and `mobile/lib/config.dart` already default to this local stack's
URLs and well-known local-dev keys, so no extra configuration is needed for local
development.

## Testing

Every layer is tested against a real running stack — no mocked backend anywhere.

```bash
# Backend: pytest (backend/tests) — real Postgres + Supabase Auth, no mocks
cd backend && pytest

# Web: Vitest (unit) + Playwright (e2e, real Supabase + backend)
cd web && npm test && npx playwright test

# Mobile: flutter test — real Supabase Auth + backend for auth/data-dependent tests
cd mobile && flutter test
```

CI (`.github/workflows/ci.yml`) runs all three suites on every push, each
provisioning its own ephemeral local Supabase stack + live backend — no secrets
required.

## Status

All phases in `/prompts` (schema, Excel parsing, version generation, PDF/QR,
OMR/ML pipeline, scan/grade service, web app, mobile app, integration testing)
are built and verified. See `docs/PROGRESS.md` for the full build log and
`docs/BLOCKERS.md` for what's still open — currently, actual Cloud Run deployment
(needs a GCP account) and the iOS release build (needs macOS/Xcode).
