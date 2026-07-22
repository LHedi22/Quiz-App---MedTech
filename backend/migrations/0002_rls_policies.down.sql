-- Rollback for 0002_rls_policies.up.sql

drop policy if exists answers_via_submission_version_quiz_owner on answers;
drop policy if exists submissions_via_version_quiz_owner on submissions;
drop policy if exists versions_via_quiz_owner on versions;
drop policy if exists questions_via_quiz_owner on questions;
drop policy if exists quizzes_owner_only on quizzes;
drop policy if exists users_own_row on users;

alter table answers disable row level security;
alter table submissions disable row level security;
alter table versions disable row level security;
alter table questions disable row level security;
alter table quizzes disable row level security;
alter table users disable row level security;

revoke select, insert, update, delete on
  users, quizzes, questions, versions, submissions, answers
  from authenticated;
revoke usage on schema public from authenticated;
