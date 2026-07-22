-- Rollback for 0001_core_tables.up.sql — drop in reverse dependency order.

drop table if exists answers;
drop table if exists submissions;
drop table if exists versions;
drop table if exists questions;
drop table if exists quizzes;
drop table if exists users;
