# Phase 1 — Database schema, RLS, migrations

## Objective
Implement the full data model from CLAUDE.md Section 4 in Supabase, with row-level
security so professors only ever see their own data, and a repeatable migration process.

## Subtask 1.1 — Core tables
**Steps:**
- Write a SQL migration file creating `users`, `quizzes`, `questions`, `versions`,
  `submissions`, `answers` exactly as specified in CLAUDE.md Section 4.
- Apply it to a local/dev Supabase instance.
- Write a rollback/down migration for each table.

**Definition of Done:**
- [ ] All 6 tables exist with correct columns, types, and foreign keys, verified via a
      script that queries `information_schema.columns`.
- [ ] Rollback migration cleanly drops all 6 tables without error.

## Subtask 1.2 — Row Level Security
**Steps:**
- Enable RLS on all 6 tables.
- Policy: a user can `select`/`insert`/`update`/`delete` a `quizzes` row only if
  `owner_id = auth.uid()`.
- Policy: `questions`, `versions` are only accessible if their parent `quiz_id` belongs to
  the requesting user.
- Policy: `submissions`, `answers` are only accessible via their parent `version_id` →
  `quiz_id` → `owner_id` chain.
- Write pytest (or SQL-based) tests using two fake users to confirm user A cannot read
  user B's quiz/questions/versions/submissions/answers.

**Definition of Done:**
- [ ] Cross-user access test suite passes: user A gets zero rows when querying user B's data.
- [ ] Same-user access test suite passes: user A gets their own rows back correctly.

## Subtask 1.3 — Seed & fixture data
**Steps:**
- Write a seed script creating one demo professor, one demo quiz with 5 MCQ questions,
  and 2 generated versions with valid `question_order`/`option_order` JSON, for use in
  later phases' manual testing.

**Definition of Done:**
- [ ] Running the seed script twice is idempotent (no duplicate rows, no errors).
- [ ] Seeded data passes a schema validation check (all JSONB fields parse, all FKs valid).

## Phase 1 Definition of Done
- [ ] All subtask DoD boxes checked.
- [ ] Migration + rollback + seed scripts committed under `/backend/migrations/`.
- [ ] PROGRESS.md updated.

## Next
Open `02_excel_upload_parsing.md`.