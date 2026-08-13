# Blockers

## Phase 7 (Next.js migration) — backend contract gap, not a credential issue [RESOLVED 2026-08-13]

**Resolution:** user chose "fix it now, then continue." Applied the same
ownership-check pattern described below to all three routes
(`excel.py::upload_quiz_excel`, `versions.py::create_versions`,
`versions.py::download_version_pdf`), each now behind
`Depends(get_current_user)` plus a `_get_owned_quiz_id` (or, for the PDF
route, a version -> quiz -> owner check after lookup) ownership check,
mirroring `quizzes.py`/`scan.py`'s existing pattern exactly. Updated every
test that called these three routes (`test_upload_endpoint.py`,
`test_pdf_storage_endpoint.py`, `test_versions_endpoint.py`, and the
`test_e2e_*.py` files) to authenticate with a real Supabase Auth user via
`create_auth_user_and_token`, and added an explicit `..._requires_auth`
test per route. Full backend suite: 137 passed (up from 134), `ruff
check`/`black --check` clean. See `docs/PROGRESS.md`'s "[Phase 7 backend
fix]" entry for the full account. The rest of this section is preserved
below as the original record of the gap.

**What's blocked:** Subtasks 7.2 (quiz creation / Excel upload / version
generation) and 7.3 (version PDF download) need three existing FastAPI
routes that currently have **no auth dependency and no ownership check at
all** - not even a valid bearer token is required:

- `POST /quizzes/{quiz_id}/upload` (`backend/app/routers/excel.py`)
- `POST /quizzes/{quiz_id}/versions` (`backend/app/routers/versions.py`)
- `GET /versions/{version_id}/pdf` (`backend/app/routers/versions.py`)

Contrast with the sibling routes in `quizzes.py` (`POST/GET /quizzes`,
`GET /quizzes/{id}/versions`, `GET /quizzes/{id}/submissions`) and
`scan.py`'s `GET/PATCH /submissions/{id}...`, which all require
`Depends(get_current_user)` plus an `owner_id`/join-based ownership check.
The `PROGRESS.md` "Phase 7 prep, cont." entry documents that exact class of
bug (broken access control, found by an automated security review) being
fixed for `/submissions/{id}` and its PATCH route - but the same review
evidently never covered `excel.py`/`versions.py`, which still let anyone
who obtains a `quiz_id` (no login required) upload arbitrary questions to
that quiz, regenerate its versions, or download any version's PDF.

**Why this is a stop-and-ask, not a fix-it-myself:** the CLAUDE.md governing
this migration explicitly added a new rule for this phase: "The backend API
contract is the shared boundary between clients... A genuine backend gap
found while building either client is a blocker to log and ask about, not
something to patch around unilaterally" (Section 2, rule 7). Adding
`Depends(get_current_user)` + an ownership check to these three routes is
exactly the kind of backend change that rule reserves for a stop-and-ask,
even though it's a small, mechanical, and clearly-scoped fix (the same
shape as the one already applied to `submissions.py`'s routes).

**What's ready to go once a decision is made:** the fix pattern already
exists twice in this codebase to copy exactly (`quizzes.py`'s
`_get_owned_quiz_id`, `scan.py`'s `_require_submission_owner`) - a
`_get_owned_quiz_id`-style check added to `excel.py`'s
`upload_quiz_excel` and `versions.py`'s `create_versions`, and a
version-to-quiz-to-owner join added to `download_version_pdf`, each behind
`Depends(get_current_user)`. Both `web/lib/api/client.ts` (this session,
Subtask 7.0) and the mobile client already send a bearer token on every
authenticated call, so closing this needs no frontend contract change on
the happy path - only the two 7.2/7.3 web screens need to actually send the
token they'll already be attaching to every other request.

**What the user needs to do:** confirm whether to (a) apply the same
ownership-check pattern to these three routes now, as a small backend fix
before continuing 7.2/7.3, (b) proceed with 7.2/7.3 against the routes
as-is and track this as a separate security follow-up, or (c) something
else. Not proceeding further into 7.2/7.3 until this is answered.

## Phase 7b.6 — CI regression: no GitHub remote configured

**What's blocked:** the DoD's literal "a single CI run on a clean branch
shows all three jobs (backend, web/Next.js, mobile) passing" - this
requires pushing to a GitHub repository and letting Actions run there.

**Why:** `git remote -v` returns nothing - this repo has never been pushed
anywhere, so there is no GitHub remote/Actions runner to trigger a real CI
run on. Not a credential issue in the usual sense (no GitHub token is
missing) - there is simply no remote repository to push to yet.

**What's ready to go once a remote exists:** `.github/workflows/ci.yml`
itself is valid (re-parsed with a YAML loader) and every one of its 9
commands across all 3 jobs was run **individually, locally, in the exact
order the workflow specifies** and passed: backend (`ruff check app
tests`, `black --check app tests`, `pytest` - 137 passed), mobile
(`flutter pub get`, `flutter analyze` - no issues, `flutter test` - 17
passed), web (`npm ci` fresh install, `npm run lint`, `npm test`, `npx
playwright install --with-deps chromium`, `npx playwright test` - 13
passed, `npm run build`). The only thing not verified is GitHub Actions'
own runner environment behaving identically to this local one, which no
amount of local re-running can substitute for.

**What the user needs to do:** push this repository to a GitHub remote
(`git remote add origin <url>`, `git push`) and confirm the resulting
Actions run is green, or share an existing remote for this session to push
to.

## Phase 10 — Deployment: genuine credential/access/platform blockers

Per CLAUDE.md Section 6 ("A credential, API key, or account access you
don't have and cannot generate yourself"), the following could not be
completed and require the user's action. Everything else in Phase 10 was
completed and verified for real without these - see PROGRESS.md's Phase
10 entries for exactly what was done in lieu of each item below.

**User decision (2026-07-25):** asked directly whether to provide GCP/
Supabase credentials now, defer the actual deploy to themselves later, or
accept the current state - chose to run the remaining deploy steps
themselves later, using the scripts prepared below (`docs/deploy_cloud_run.sh`,
`backend/migrations/apply_migrations.py`). No further agent action is
expected on items 1-3 until the user runs those steps or shares access.

### 1. Google Cloud Run deployment (Subtask 10.1)

**What's blocked:** actually running `docs/deploy_cloud_run.sh` (the
`gcloud run deploy` command sequence) to get a live Cloud Run service URL,
and therefore the DoD's literal "`GET /health` on the deployed Cloud Run
URL returns 200 from an external client" and "E2E smoke test passes
against the deployed environment."

**Why:** this machine has no `gcloud` CLI installed and no authenticated
GCP account. There is no GCP project or billing account on record to
deploy into.

**What's ready to go once access exists:**
- `backend/Dockerfile` - built and smoke-tested locally (`docker build` +
  `docker run` + `GET /health` returns 200 from the host).
- `docs/deploy_cloud_run.sh` - the exact deploy command, including wiring
  CLAUDE.md Section 8's env vars through Secret Manager (not hardcoded).
- `backend/scripts/e2e_smoke_test.py` - the Phase-9-style smoke test,
  already verified end-to-end (exact expected score) against the same
  application code; just needs `BACKEND_URL` pointed at the real Cloud Run
  URL once one exists.

**What the user needs to do:** provide (or grant access to) a GCP project
with billing enabled, and either run `gcloud auth login` + the deploy
script directly, or share credentials/access for this session to do it.

### 2. A hosted (non-local) production Supabase project (Subtask 10.2) [RESOLVED 2026-08-14]

**Resolution:** user provided access to an existing hosted project ("Quiz
App - MedTech", ref `iuwallqxodwjeeraqwop`, eu-west-1), authenticated via
`supabase login` (their own browser flow, not shared with the agent).
`backend/migrations/apply_migrations.py` ran unmodified against it -
`information_schema.tables` shows exactly the 6 expected tables, 6 RLS
policies present, seed data landed (1 professor/1 quiz/5 questions/2
versions). Discovery: the project's direct-connection host
(`db.<ref>.supabase.co`) resolves IPv6-only and this network has no IPv6
route (`getaddrinfo failed`) - not a credential issue, a networking one;
switched to the Session Pooler connection string
(`postgres.<ref>@aws-0-<region>.pooler.supabase.com:5432`, IPv4-reachable)
instead, which the migration script accepts unmodified since it only reads
`DATABASE_URL`. The DB password was never entered into the conversation -
the user wrote it directly into a gitignored `backend/.env.production`
file, and every command referencing it downstream was piped through a
redaction filter before being shown, so the connection string never
appears in this transcript.

Also applied the "minor, mechanical change" this entry already anticipated:
`test_rls_cross_user.py`'s `run_sql` helper shelled out to
`docker exec <container> psql`, which has no equivalent against a hosted
project - replaced with a direct `psycopg.connect(DATABASE_URL)` call
(matching `app/db.py`'s own connection pattern exactly), defaulting to the
same local connection string used everywhere else in this test suite so
local runs are unaffected. Re-ran the full 12-test suite against **both**
targets to confirm no regression: local (12 passed) and the hosted
project (12 passed) - all cross-user isolation and own-data-visibility
assertions hold identically in both environments. This also surfaced and
fixed a real, previously-latent bug in the fixture's own teardown SQL: it
deleted `users` before deleting the `quizzes` row still referencing it via
`owner_id` (no `ON DELETE CASCADE` on that column, unlike `questions`/
`versions`, which cascade off `quizzes`) - a `ForeignKeyViolation` on
first run against the hosted project (a case the previous local-only
verification evidently never actually exercised cleanly, despite Phase
1.2's "all 12 pass" log entry). Fixed by deleting `submissions` and
`quizzes` before `users` in the teardown; leftover rows from the one
failed run were manually cleaned up and the hosted project's row counts
verified back to exactly the seeded state (1 user, 1 quiz) afterward.

**Operational note, not itself a blocker:** the `api-keys` CLI command
used to retrieve this project's anon/service_role keys printed the full
legacy `service_role` JWT in plaintext into this session (the newer
`sb_secret_...` key came back properly redacted; the legacy JWT-format key
did not) - flagged to the user immediately, who was advised to rotate that
specific legacy key in the dashboard since it now sits in this
transcript. The anon/publishable key is meant to be public and needs no
rotation. Full backend suite re-verified at 137 passing (unchanged) after
this fix; `ruff check`/`black --check` clean.

**Still open:** applying the exact same, now-hosted-verified script/test
pair to this project's *own* `DATABASE_URL`/`SUPABASE_URL` env vars for
routine local development is unaffected (defaults unchanged); this section
now only tracks whether the user wants the hosted project used for
anything beyond this verification (e.g. as the actual `DATABASE_URL` a
deployed Cloud Run service would use) - see blocker #1 below, still open.

---

**Original blocker record, preserved below:**

**What's blocked:** applying `backend/migrations/apply_migrations.py` to
an actual hosted production Supabase project's Postgres instance, and the
DoD's literal "Cross-user RLS test passes against production."

**Why:** `supabase projects list` returns `LegacyPlatformAuthRequiredError`
- no Supabase access token/login is available in this session, and no
hosted project reference exists anywhere in the repo's config.

**What's ready to go once access exists:** the migration script and the
real `backend/tests/test_rls_cross_user.py` suite were both verified
against a genuinely fresh local Supabase instance (distinct project,
distinct ports, not a reused/pre-migrated one) - zero manual intervention
needed, all 12 RLS tests passed. The exact same commands work unmodified
against a real hosted project:
```
DATABASE_URL=<prod-connection-string> python migrations/apply_migrations.py
SUPABASE_URL=<prod-url> SUPABASE_ANON_KEY=<prod-anon-key> \
  SUPABASE_SERVICE_ROLE_KEY=<prod-service-role-key> \
  pytest backend/tests/test_rls_cross_user.py
```
(`test_rls_cross_user.py`'s SQL-execution helper currently shells out to
`docker exec <container> psql` for setup/cleanup queries, which assumes a
local Docker container; against a real hosted project this would need a
small adjustment to use a direct `psycopg`/`psql` connection instead - a
minor, mechanical change once a real prod `DATABASE_URL` exists, not a
blocker in itself.)

**What the user needs to do:** create (or share access to) a hosted
Supabase project - project URL, anon key, service role key, and Postgres
connection string.

### 3. iOS release build (IPA) (Subtask 10.3)

**What's blocked:** `flutter build ipa` and the DoD's "release... IPA...
without errors."

**Why:** this is a platform constraint, not a credential gap - building an
iOS IPA requires Xcode, which only runs on macOS. This is a Windows 11
machine (confirmed via `flutter doctor`, which lists no iOS toolchain).
Even with an Apple Developer account's credentials, there is no macOS
environment available in this session to invoke Xcode's build toolchain.

**What was done instead:** the Android release APK was built successfully
(see PROGRESS.md Phase 10.3), and the iOS project's bundle identifier
(`com.medtech.examscanner.examScannerMobile`) is already configured in
`mobile/ios/Runner.xcodeproj/project.pbxproj`, consistent with Android's
`applicationId`. `mobile/lib/config.dart`'s `--dart-define` mechanism is
platform-agnostic, so the same production-pointing build command works for
iOS once run on macOS: `flutter build ipa --release --dart-define=...`.

**What the user needs to do:** run `flutter build ipa` on a Mac (with
Xcode and, for a real signed IPA ready for TestFlight/App Store, an Apple
Developer Program account), or grant access to a macOS CI runner.

### 4. This machine's C: drive is critically low on disk space (not a Phase 10 credential blocker - a machine-health issue found during it)

**What happened:** building the mobile release APK (Subtask 10.3) required
downloading the Android NDK (~1GB), Build-Tools 36, Platform 36, and CMake,
on top of this session's Docker images/Supabase stacks/Gradle and pip
caches. Free space on `C:` dropped to ~4MB at one point, which corrupted
one internal file copy mid-build (safely recovered - see PROGRESS.md Phase
10.3; the actual build artifact was unaffected and independently verified
valid). A safely-scoped ~300MB was freed (a leftover NDK download temp
file, this session's own local backend Docker image) without touching any
of the user's other Docker containers/volumes/images, since those weren't
created by this session and deleting them without asking risks real data
loss for unrelated work (the machine also runs a pre-existing `quizapp`
Supabase stack).

**Current state:** still only ~0.26GB free as of the end of this session.

**What the user needs to do:** free up disk space before doing further
local Android/Docker-heavy work on this machine - e.g. `docker system
prune` (review first; this machine has other projects' containers/images),
clearing old Android SDK caches, or freeing space via normal Windows disk
cleanup. Not urgent to Phase 10's own completion (everything it needed is
already done), but worth doing before the next build-heavy session.
