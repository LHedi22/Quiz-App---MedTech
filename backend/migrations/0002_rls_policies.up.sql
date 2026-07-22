-- Phase 1.2 — enable RLS on all 6 tables, scoped to the requesting professor.
--
-- GRANTs are required in addition to RLS policies: PostgREST/Supabase's Data API
-- only reaches tables the `authenticated` role has been granted access to at all;
-- RLS policies then filter which *rows* within that grant are visible. Without
-- these grants every request 403s outright, regardless of policy correctness.
grant usage on schema public to authenticated;
grant select, insert, update, delete on
  users, quizzes, questions, versions, submissions, answers
  to authenticated;

alter table users enable row level security;
alter table quizzes enable row level security;
alter table questions enable row level security;
alter table versions enable row level security;
alter table submissions enable row level security;
alter table answers enable row level security;

-- users: a professor can only see/manage their own profile row.
create policy users_own_row on users
  for all
  using (id = auth.uid())
  with check (id = auth.uid());

-- quizzes: owner_id must match the requesting user.
create policy quizzes_owner_only on quizzes
  for all
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

-- questions: accessible only if the parent quiz belongs to the requesting user.
create policy questions_via_quiz_owner on questions
  for all
  using (
    exists (
      select 1 from quizzes
      where quizzes.id = questions.quiz_id
        and quizzes.owner_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from quizzes
      where quizzes.id = questions.quiz_id
        and quizzes.owner_id = auth.uid()
    )
  );

-- versions: accessible only if the parent quiz belongs to the requesting user.
create policy versions_via_quiz_owner on versions
  for all
  using (
    exists (
      select 1 from quizzes
      where quizzes.id = versions.quiz_id
        and quizzes.owner_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from quizzes
      where quizzes.id = versions.quiz_id
        and quizzes.owner_id = auth.uid()
    )
  );

-- submissions: accessible via version_id -> quiz_id -> owner_id.
create policy submissions_via_version_quiz_owner on submissions
  for all
  using (
    exists (
      select 1 from versions
      join quizzes on quizzes.id = versions.quiz_id
      where versions.id = submissions.version_id
        and quizzes.owner_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from versions
      join quizzes on quizzes.id = versions.quiz_id
      where versions.id = submissions.version_id
        and quizzes.owner_id = auth.uid()
    )
  );

-- answers: accessible via submission_id -> version_id -> quiz_id -> owner_id.
create policy answers_via_submission_version_quiz_owner on answers
  for all
  using (
    exists (
      select 1 from submissions
      join versions on versions.id = submissions.version_id
      join quizzes on quizzes.id = versions.quiz_id
      where submissions.id = answers.submission_id
        and quizzes.owner_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from submissions
      join versions on versions.id = submissions.version_id
      join quizzes on quizzes.id = versions.quiz_id
      where submissions.id = answers.submission_id
        and quizzes.owner_id = auth.uid()
    )
  );
