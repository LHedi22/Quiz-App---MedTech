-- Phase 1.3 — seed one demo professor, one demo quiz with 5 MCQ questions, and
-- 2 generated versions with valid question_order / option_order JSON.
--
-- Idempotent: uses fixed UUIDs and ON CONFLICT so re-running produces no duplicates
-- and no errors. Run as postgres/service-role (bypasses RLS by design — this is
-- fixture data for manual testing in later phases, not a professor-facing action).

insert into users (id, email, role)
values ('00000000-0000-0000-0000-000000000001', 'demo.professor@example.com', 'professor')
on conflict (id) do update set email = excluded.email, role = excluded.role;

insert into quizzes (id, owner_id, title)
values (
  '00000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000001',
  'Demo Quiz — Intro to Cell Biology'
)
on conflict (id) do update set owner_id = excluded.owner_id, title = excluded.title;

insert into questions (id, quiz_id, text, options, correct_option, order_index)
values
  ('00000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000002',
   'What is the powerhouse of the cell?',
   '["Nucleus", "Mitochondria", "Ribosome", "Golgi apparatus"]', 'B', 1),
  ('00000000-0000-0000-0000-000000000012', '00000000-0000-0000-0000-000000000002',
   'Which molecule carries genetic information?',
   '["ATP", "RNA polymerase", "DNA", "Glucose"]', 'C', 2),
  ('00000000-0000-0000-0000-000000000013', '00000000-0000-0000-0000-000000000002',
   'What process do plants use to convert light into energy?',
   '["Respiration", "Fermentation", "Photosynthesis", "Osmosis"]', 'C', 3),
  ('00000000-0000-0000-0000-000000000014', '00000000-0000-0000-0000-000000000002',
   'What is the basic structural unit of all living organisms?',
   '["Atom", "Cell", "Tissue", "Organ"]', 'B', 4),
  ('00000000-0000-0000-0000-000000000015', '00000000-0000-0000-0000-000000000002',
   'Which organelle is responsible for protein synthesis?',
   '["Lysosome", "Vacuole", "Ribosome", "Peroxisome"]', 'C', 5)
on conflict (id) do update set
  quiz_id = excluded.quiz_id,
  text = excluded.text,
  options = excluded.options,
  correct_option = excluded.correct_option,
  order_index = excluded.order_index;

insert into versions (id, quiz_id, version_number, qr_id, question_order, option_order)
values
  (
    '00000000-0000-0000-0000-000000000021',
    '00000000-0000-0000-0000-000000000002',
    1,
    'demo-quiz-v1',
    '["00000000-0000-0000-0000-000000000013", "00000000-0000-0000-0000-000000000011", '
    '"00000000-0000-0000-0000-000000000015", "00000000-0000-0000-0000-000000000012", '
    '"00000000-0000-0000-0000-000000000014"]',
    '{
      "00000000-0000-0000-0000-000000000011": [1, 3, 0, 2],
      "00000000-0000-0000-0000-000000000012": [2, 0, 3, 1],
      "00000000-0000-0000-0000-000000000013": [3, 1, 2, 0],
      "00000000-0000-0000-0000-000000000014": [0, 2, 1, 3],
      "00000000-0000-0000-0000-000000000015": [2, 3, 1, 0]
    }'
  ),
  (
    '00000000-0000-0000-0000-000000000022',
    '00000000-0000-0000-0000-000000000002',
    2,
    'demo-quiz-v2',
    '["00000000-0000-0000-0000-000000000012", "00000000-0000-0000-0000-000000000014", '
    '"00000000-0000-0000-0000-000000000011", "00000000-0000-0000-0000-000000000015", '
    '"00000000-0000-0000-0000-000000000013"]',
    '{
      "00000000-0000-0000-0000-000000000011": [3, 0, 1, 2],
      "00000000-0000-0000-0000-000000000012": [1, 2, 0, 3],
      "00000000-0000-0000-0000-000000000013": [0, 3, 2, 1],
      "00000000-0000-0000-0000-000000000014": [2, 1, 3, 0],
      "00000000-0000-0000-0000-000000000015": [1, 0, 2, 3]
    }'
  )
on conflict (id) do update set
  quiz_id = excluded.quiz_id,
  version_number = excluded.version_number,
  qr_id = excluded.qr_id,
  question_order = excluded.question_order,
  option_order = excluded.option_order;
