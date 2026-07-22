-- Phase 1.1 — core tables, exactly as specified in CLAUDE.md Section 4.

create table users (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  role text not null default 'professor',
  created_at timestamptz not null default now()
);

create table quizzes (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references users(id),
  title text not null,
  created_at timestamptz not null default now()
);

create table questions (
  id uuid primary key default gen_random_uuid(),
  quiz_id uuid not null references quizzes(id) on delete cascade,
  text text not null,
  options jsonb not null,
  correct_option text not null,
  order_index int not null
);

create table versions (
  id uuid primary key default gen_random_uuid(),
  quiz_id uuid not null references quizzes(id) on delete cascade,
  version_number int not null,
  qr_id text unique not null,
  question_order jsonb not null,
  option_order jsonb not null,
  created_at timestamptz not null default now()
);

create table submissions (
  id uuid primary key default gen_random_uuid(),
  version_id uuid not null references versions(id),
  student_id text,
  total_score float,
  status text not null default 'pending',
  created_at timestamptz not null default now()
);

create table answers (
  id uuid primary key default gen_random_uuid(),
  submission_id uuid not null references submissions(id) on delete cascade,
  question_no int not null,
  detected_option text,
  confidence float not null,
  flagged boolean not null default false,
  correct boolean,
  score float
);
