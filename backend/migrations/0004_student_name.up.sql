-- Phase: handwritten student-name detection.
--
-- student_name/name_confidence/name_flagged mirror the answers table's
-- confidence/flagged pattern (CLAUDE.md Section 2 rule 5's confidence gate
-- applies here too - OCR reads of a handwritten name are never
-- auto-trusted below threshold). Kept separate from the existing
-- student_id text column, which stays untouched: student_id is an
-- opaque, optionally-supplied identifier, while student_name is what the
-- scanner reads off the printed name field.

alter table submissions
  add column student_name text,
  add column name_confidence float,
  add column name_flagged boolean not null default false;
