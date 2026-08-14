# CLAUDE.md — Exam Version Generator & Scanner
## Single source of truth for this project. Read this file fully before doing anything.

---

## 1. What this project is

A professor-only tool that solves exam cheating caused by manual quiz-version creation.

**The problem:** to prevent cheating, professors manually create multiple versions of the
same quiz (shuffled question order, shuffled answer order per question), then must grade
each version separately by hand, tracking which shuffle maps to which original answer key.
This is slow and error-prone.

**The solution:**
1. Professor uploads one Excel sheet: MCQ questions + options + correct answers.
2. The app generates N versions (professor chooses N), each with independently shuffled
   question order AND answer-option order.
3. Each version gets a printable PDF with a QR code encoding its version ID.
4. Professor prints, distributes, administers the exam on paper.
5. Professor scans each completed answer sheet with the mobile app.
6. The app decodes the QR code, looks up that version's mapping, detects filled bubbles,
   translates positions back to canonical questions, and scores against the master key.
7. Low-confidence detections (unclear marks, unreadable QR, multiple marks) are flagged
   for professor review on the web app. Everything else finalizes automatically.

**Two clients, one backend:**
- **Web app** — professor's control center, built in **Next.js (TypeScript)**. Quiz
  creation, Excel upload, version generation, PDF download, results dashboard,
  flagged-answer review.
- **Mobile app** — scanning only, built in **Flutter**. Camera-first, batch-scan a stack
  of papers fast, queue results, sync to backend.

> **Migration note (post-launch pivot):** the web app was originally built in Flutter web
> and was migrated to Next.js to decouple web iteration speed from the mobile release
> cycle. The mobile app was **not** affected by this migration and remains Flutter. See
> `07_web_app_nextjs.md` (build) and `07b_web_migration_testing.md` (regression) for the
> migration itself. Any future references to "the web app" in this file describe the
> current Next.js implementation, not the retired Flutter-web one.

## 2. Non-negotiable rules

1. **No LLM calls anywhere in this system.** Not for grading, not for parsing, not for
   anything. Every step is either deterministic logic or a small trained classical ML
   model (e.g. scikit-learn / lightweight CNN for bubble-fill detection). If you find
   yourself reaching for an LLM API call to solve a problem, stop and re-read this rule —
   solve it with rule-based logic or a trained classifier instead.
2. **MCQ only.** No short answer, no essay, no open-ended grading. Do not build for
   question types beyond multiple choice unless explicitly told to.
3. **The `versions` table mapping is the most important data in this system.** Losing or
   corrupting `question_order` / `option_order` for a version means that version can never
   be scored correctly. Never write destructive migrations against this table without a
   backup step. Never allow a version to be re-shuffled after its PDF has been generated.
4. **Every subtask has a Definition of Done (DoD).** Do not consider a subtask complete
   until every DoD item is verified true — by running tests, not by assuming.
5. **Confidence gate is mandatory wherever OMR detection happens.** Never auto-finalize a
   score when: QR code unreadable, zero bubbles filled, multiple bubbles filled, or
   classifier confidence below threshold. Always route those to professor review.
6. **Commit after every completed subtask** with a clear conventional-commit message.
   Never leave uncommitted working code at the end of a session.
7. **The backend API contract is the shared boundary between clients.** Neither client
   redesigns FastAPI routes or schemas to suit its own convenience. A genuine backend gap
   found while building either client is a blocker to log and ask about, not something to
   patch around unilaterally.

## 3. Tech stack

| Layer              | Choice                                                            |
|---------------------|--------------------------------------------------------------------|
| Backend             | FastAPI (Python), deployed on Google Cloud Run                    |
| Database/Auth       | Supabase (Postgres + Auth + Storage)                               |
| Web client          | **Next.js 15+ (App Router, TypeScript), Tailwind CSS**            |
| Web auth/session    | **`@supabase/supabase-js` + `@supabase/ssr`**                     |
| Web data fetching   | **React Query or SWR** (client-side refetch/optimistic updates)   |
| Web testing         | **Vitest + React Testing Library (unit/component), Playwright (e2e)** |
| Web hosting         | **Vercel, or static export via Firebase Hosting / Cloud Storage + CDN** |
| Mobile client       | Flutter (iOS + Android) — **unchanged**                           |
| CV / OMR            | OpenCV (alignment, bubble region detection)                        |
| Bubble classifier   | scikit-learn or a small CNN (TensorFlow/PyTorch), trained on labeled bubble crops |
| QR generation       | `qrcode` (Python)                                                   |
| QR decoding         | `pyzbar` or OpenCV's `QRCodeDetector`                              |
| PDF generation      | ReportLab or WeasyPrint                                             |
| Excel parsing       | `openpyxl` / `pandas`                                              |
| Testing (backend/mobile) | `pytest` (backend), `flutter test` (mobile)                  |

## 4. Data model (Postgres / Supabase)

```sql
create table users (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  role text not null default 'professor',
  created_at timestamptz not null default now()
);

create table quizzes (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references users(id),
  title text not null,
  created_at timestamptz not null default now()
);

create table questions (
  id uuid primary key default gen_random_uuid(),
  quiz_id uuid not null references quizzes(id) on delete cascade,
  text text not null,
  options jsonb not null,          -- ["Option A text", "Option B text", ...]
  correct_option text not null,    -- e.g. "A" (canonical, pre-shuffle)
  order_index int not null         -- canonical order in the source Excel
);

create table versions (
  id uuid primary key default gen_random_uuid(),
  quiz_id uuid not null references quizzes(id) on delete cascade,
  version_number int not null,
  qr_id text unique not null,               -- encoded in the printed QR code
  question_order jsonb not null,            -- [canonical_question_id, ...] in shuffled order
  option_order jsonb not null,              -- {question_id: [canonical_option_index,...]}
  created_at timestamptz not null default now()
);

create table submissions (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references versions(id),
  student_id text,                          -- optional, nullable
  student_name text,                        -- OCR-read from the printed name field, nullable
  name_confidence float,                    -- Tesseract's 0-100 word-confidence, nullable
  name_flagged boolean not null default false, -- confidence gate: true routes to needs_review
  total_score float,
  status text not null default 'pending',   -- pending | finalized | needs_review
  created_at timestamptz not null default now()
);

create table answers (
  id uuid primary key default gen_random_uuid(),
  submission_id uuid not null references submissions(id) on delete cascade,
  question_no int not null,                 -- canonical question number
  detected_option text,                     -- canonical option letter, nullable if unreadable
  confidence float not null,
  flagged boolean not null default false,
  correct boolean,
  score float
);
```

Row Level Security: every table is scoped so a professor (`owner_id` / joined via
`quiz_id`) can only see their own quizzes, versions, submissions, and answers. RLS
policies live in Phase 1 and must behave identically regardless of which client
(Next.js web or Flutter mobile) is making the request — see `07b_web_migration_testing.md`
Subtask 7b.2 for the web-specific SSR regression check.

## 5. Repo structure

```
/backend                FastAPI app
  /app
    /routers             excel.py, versions.py, scan.py, results.py
    /services             parsing.py, shuffler.py, pdf_gen.py, qr.py, omr.py, scoring.py
    /models                pydantic schemas
    /ml                     bubble_classifier/ (training script, model artifact, inference)
  /tests

/web                     Next.js (TypeScript) web app — professor dashboard
  /app                    App Router routes (auth, quizzes, results, review)
  /components             shared React components
  /lib
    /api                   typed API client wrapping FastAPI calls
    /supabase               Supabase client (browser) + server helpers
  /middleware.ts           server-side auth route guarding
  /tests                    Vitest/RTL unit + component tests
  /e2e                       Playwright e2e tests

/mobile                  Flutter mobile app (scanning only) — unchanged

/shared                  Shared Dart package (mobile-only now; API client, models,
                         constants). Do NOT assume this is shared with /web — the web
                         app has its own TypeScript API client under /web/lib/api/.

/prompts                 Phase prompt files (this is what you work through, in order)
/docs
  PROGRESS.md             agent updates this after every subtask
  BLOCKERS.md              agent writes here ONLY when truly stuck; otherwise keep empty
CLAUDE.md                 this file
```

## 6. The autonomous agent loop (read this section every session)

You will work through `/prompts/00_setup.md`, then `01_...md`, `02_...md`, etc., **in
numeric order, without stopping between them, and without waiting for user confirmation**,
unless you hit a genuine blocker (see below). Note the non-integer-numbered file
`07b_web_migration_testing.md`, which runs immediately after `07_web_app_nextjs.md` and
before `08_mobile_app.md` — treat it as a mandatory step in the same sequence, not an
optional extra.

For every subtask inside a prompt file, follow this loop exactly:

1. **Read** the subtask's Goal, Steps, and Definition of Done (DoD).
2. **Implement** the steps.
3. **Self-test**: run the relevant test suite (`pytest`, `flutter test`, `npm test` /
   `npx playwright test`, or manual script as specified). If tests don't exist yet for
   this subtask, write them first as part of the steps — do not skip testing because
   "it's simple."
4. **Verify DoD**: go through every DoD checkbox one by one. If any fails, return to step 2
   and fix it. Do not mark a subtask done based on assumption — only based on a passing
   check you actually ran.
5. **Repeat steps 2–4** until every DoD item is genuinely true. This is the "objective
   achievement loop" — you do not stop, ask for help, or move on with a partially-met DoD.
6. **Log** a one-line entry in `/docs/PROGRESS.md`: `[Phase N.Subtask M] <what was done> — DoD verified.`
7. **Commit**: `git commit -m "phaseN: <subtask summary>"`.
8. **Move to the next subtask** in the same file. When the file's subtasks are all done,
   verify the file's overall Phase Definition of Done, then open the next numbered file in
   `/prompts/` and repeat from step 1.

**When to actually stop and ask the user:**
- A credential, API key, or account access you don't have and cannot generate yourself.
- An ambiguity in product behavior that isn't answered anywhere in this file or the prompt
  file, and where guessing wrong would require significant rework (e.g. a genuinely new
  feature decision, not an implementation detail).
- A DoD check that fails repeatedly (3+ attempts) for reasons outside your control (e.g. a
  third-party service outage).

In these cases: write the blocker clearly to `/docs/BLOCKERS.md` with what you tried, then
stop and summarize the blocker for the user. Do not stop for anything else — implementation
details, styling choices, and minor ambiguities should be resolved by picking the most
sensible option consistent with this file, noting the assumption in `PROGRESS.md`, and
continuing.

## 7. Coding standards

- **Python**: type-hinted, `black`-formatted, `ruff`-linted. Pydantic models for all
  request/response schemas. No bare `except:`.
- **TypeScript / Next.js (web)**: strict mode enabled in `tsconfig.json`. `eslint` +
  `prettier` enforced via `npm run lint` / `npm run format`. Prefer server components
  and server-side data fetching by default; use client components only where
  interactivity requires it. All API calls go through `/web/lib/api/`, never ad-hoc
  `fetch` calls scattered through components. No `any` types without an inline comment
  explaining why. Tests: Vitest + React Testing Library for components/logic, Playwright
  for user-facing flows — every non-trivial page/flow gets at least one Playwright test,
  matching the DoD bar in each web-related prompt file, not less.
- **Dart/Flutter (mobile only)**: `dart format`, follow effective Dart style guide.
  Widgets kept small and composable. State management: Riverpod (unless a strong reason
  emerges to switch — if so, log the reason in PROGRESS.md before switching).
- **Naming**: snake_case for Python and SQL, camelCase for Dart and TypeScript,
  kebab-case for file names outside code (docs, prompts).
- **Tests are mandatory**, not optional, for every backend service function, every
  non-trivial mobile widget/screen, and every non-trivial web page/flow. Aim for the DoD
  in each prompt file as the test bar, not less.
- **Git**: one commit per subtask, conventional commit prefixes (`feat:`, `fix:`,
  `test:`, `docs:`, `chore:`).

## 8. Environment variables

```
# Backend
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=
CLOUD_RUN_SERVICE_NAME=
ENV=development|staging|production

# Web (Next.js) — NEXT_PUBLIC_* are exposed to the browser, keep the rest server-only
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_BASE_URL=
```

No LLM API keys should ever be required by this project. If a prompt file or a piece of
generated code asks you to add one, that's a signal something has drifted from the spec —
stop and re-check against Section 2.

## 9. Phase index

Work through these in order. Do not skip ahead even if a later phase seems easy. Note
`7b`, inserted specifically to validate the Flutter→Next.js web migration before mobile
work resumes.

| #  | File                              | Phase                                                             |
|----|-------------------------------------|--------------------------------------------------------------------|
| 0  | `00_setup.md`                       | Repo scaffolding, tooling, CI skeleton                             |
| 1  | `01_database_schema.md`             | Supabase schema, RLS, migrations                                   |
| 2  | `02_excel_upload_parsing.md`        | Excel upload + validation + parsing service                        |
| 3  | `03_version_generation.md`          | Shuffle engine (questions + options per version)                   |
| 4  | `04_pdf_qr_generation.md`           | PDF rendering + QR code embedding + storage                        |
| 5  | `05_omr_ml_pipeline.md`             | Bubble classifier training + OMR detection engine                  |
| 6  | `06_scan_grade_service.md`          | Scan pipeline: decode → align → detect → translate → score → confidence gate |
| 7  | `07_web_app_nextjs.md`              | **Next.js web app**: professor dashboard (migrated from Flutter web) |
| 7b | `07b_web_migration_testing.md`      | **Web migration regression & full-system verification**            |
| 8  | `08_mobile_app.md`                  | Flutter mobile: scanning-only flow                                 |
| 9  | `09_integration_testing.md`         | End-to-end tests across both clients + backend                     |
| 10 | `10_deployment.md`                  | Cloud Run deploy, Supabase prod config, release                    |

## 10. How to run locally

```bash
# backend
cd backend && uvicorn app.main:app --reload

# web
cd web && npm run dev

# mobile
cd mobile && flutter run
```

Read the current phase's prompt file now and begin.
