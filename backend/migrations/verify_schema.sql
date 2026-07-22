-- Verification script for Subtask 1.1 DoD: confirm all 6 tables exist with the
-- exact columns, types, and nullability specified in CLAUDE.md Section 4.

select table_name, column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public'
  and table_name in ('users', 'quizzes', 'questions', 'versions', 'submissions', 'answers')
order by table_name, ordinal_position;
