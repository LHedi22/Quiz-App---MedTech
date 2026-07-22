"""Validation for Phase 1.3 seed data: JSONB fields parse into sane shapes and all
foreign keys resolve. Requires a local Supabase stack with 0001-0003 applied;
skips cleanly if one isn't reachable.
"""

import json
import subprocess

import httpx
import pytest

SUPABASE_URL = "http://127.0.0.1:54341"
DB_CONTAINER = "supabase_db_exam_scanner"

DEMO_QUIZ_ID = "00000000-0000-0000-0000-000000000002"
DEMO_PROFESSOR_ID = "00000000-0000-0000-0000-000000000001"


def _supabase_reachable() -> bool:
    try:
        httpx.get(f"{SUPABASE_URL}/auth/v1/health", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _supabase_reachable(),
    reason="local Supabase stack not reachable (run `supabase start` in /backend)",
)


def query_json(sql: str):
    result = subprocess.run(
        ["docker", "exec", "-i", DB_CONTAINER, "psql", "-U", "postgres", "-d", "postgres", "-tA"],
        input=f"select to_jsonb(t) from ({sql}) t;",
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


@pytest.fixture(scope="module")
def seeded_questions():
    rows = query_json(
        f"select id, options, correct_option from questions where quiz_id = '{DEMO_QUIZ_ID}'"
    )
    assert len(rows) == 5, "seed script should produce exactly 5 questions"
    return {row["id"]: row for row in rows}


@pytest.fixture(scope="module")
def seeded_versions():
    rows = query_json(
        f"select id, version_number, question_order, option_order "
        f"from versions where quiz_id = '{DEMO_QUIZ_ID}' order by version_number"
    )
    assert len(rows) == 2, "seed script should produce exactly 2 versions"
    return rows


def test_professor_and_quiz_fk_chain_resolves():
    rows = query_json(
        f"select q.id as quiz_id, q.owner_id, u.id as user_id "
        f"from quizzes q join users u on u.id = q.owner_id "
        f"where q.id = '{DEMO_QUIZ_ID}'"
    )
    assert len(rows) == 1
    assert rows[0]["owner_id"] == DEMO_PROFESSOR_ID == rows[0]["user_id"]


def test_question_order_is_a_permutation_of_the_quizzes_questions(
    seeded_questions, seeded_versions
):
    expected_ids = set(seeded_questions.keys())
    for version in seeded_versions:
        order = version["question_order"]
        assert isinstance(order, list)
        assert set(order) == expected_ids, (
            f"version {version['version_number']}'s question_order does not exactly "
            f"cover the quiz's 5 questions"
        )
        assert len(order) == len(set(order)), "question_order contains duplicates"


def test_option_order_covers_every_question_with_a_valid_permutation(
    seeded_questions, seeded_versions
):
    for version in seeded_versions:
        option_order = version["option_order"]
        assert isinstance(option_order, dict)
        assert set(option_order.keys()) == set(seeded_questions.keys())
        for question_id, permutation in option_order.items():
            option_count = len(seeded_questions[question_id]["options"])
            assert sorted(permutation) == list(range(option_count)), (
                f"option_order for question {question_id} in version "
                f"{version['version_number']} is not a valid permutation of its options"
            )


def test_correct_option_is_a_valid_letter_for_its_options(seeded_questions):
    for question_id, question in seeded_questions.items():
        option_count = len(question["options"])
        valid_letters = [chr(ord("A") + i) for i in range(option_count)]
        assert question["correct_option"] in valid_letters, (
            f"question {question_id} has correct_option "
            f"{question['correct_option']!r} outside its {option_count} options"
        )
