-- Rollback for 0006_manual_edit_audit.up.sql.

alter table answers
  drop column if exists manually_edited,
  drop column if exists edited_at;

alter table submissions
  drop column if exists name_manually_edited;
