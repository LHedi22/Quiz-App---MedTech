-- Rollback for 0004_student_name.up.sql.

alter table submissions
  drop column if exists student_name,
  drop column if exists name_confidence,
  drop column if exists name_flagged;
