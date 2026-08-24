-- Rollback for 0005_scan_capture_id.up.sql.

drop index if exists submissions_capture_id_key;

alter table submissions
  drop column if exists capture_id;
