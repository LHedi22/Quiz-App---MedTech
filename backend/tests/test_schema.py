"""Verifies the 6 core tables from Phase 1.1 match CLAUDE.md Section 4 exactly,
via information_schema.columns and foreign key metadata. Requires a local
Supabase stack with 0001_core_tables.up.sql applied; skips cleanly otherwise.
"""

import subprocess

import httpx
import pytest

SUPABASE_URL = "http://127.0.0.1:54341"
DB_CONTAINER = "supabase_db_exam_scanner"

EXPECTED_COLUMNS = {
    "users": {
        "id": ("uuid", "NO"),
        "email": ("text", "NO"),
        "role": ("text", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
    },
    "quizzes": {
        "id": ("uuid", "NO"),
        "owner_id": ("uuid", "NO"),
        "title": ("text", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
    },
    "questions": {
        "id": ("uuid", "NO"),
        "quiz_id": ("uuid", "NO"),
        "text": ("text", "NO"),
        "options": ("jsonb", "NO"),
        "correct_option": ("text", "NO"),
        "order_index": ("integer", "NO"),
    },
    "versions": {
        "id": ("uuid", "NO"),
        "quiz_id": ("uuid", "NO"),
        "version_number": ("integer", "NO"),
        "qr_id": ("text", "NO"),
        "question_order": ("jsonb", "NO"),
        "option_order": ("jsonb", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
    },
    "submissions": {
        "id": ("uuid", "NO"),
        "version_id": ("uuid", "NO"),
        "student_id": ("text", "YES"),
        "student_name": ("text", "YES"),
        "name_confidence": ("double precision", "YES"),
        "name_flagged": ("boolean", "NO"),
        "total_score": ("double precision", "YES"),
        "status": ("text", "NO"),
        "created_at": ("timestamp with time zone", "NO"),
        "capture_id": ("text", "YES"),
    },
    "answers": {
        "id": ("uuid", "NO"),
        "submission_id": ("uuid", "NO"),
        "question_no": ("integer", "NO"),
        "detected_option": ("text", "YES"),
        "confidence": ("double precision", "NO"),
        "flagged": ("boolean", "NO"),
        "correct": ("boolean", "YES"),
        "score": ("double precision", "YES"),
    },
}

EXPECTED_FOREIGN_KEYS = {
    ("questions", "quiz_id"): ("quizzes", "id", "CASCADE"),
    ("versions", "quiz_id"): ("quizzes", "id", "CASCADE"),
    ("quizzes", "owner_id"): ("users", "id", "NO ACTION"),
    ("submissions", "version_id"): ("versions", "id", "NO ACTION"),
    ("answers", "submission_id"): ("submissions", "id", "CASCADE"),
}


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


def run_sql_tsv(sql: str) -> list[list[str]]:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            DB_CONTAINER,
            "psql",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-tA",
            "-F",
            "\t",
        ],
        input=sql,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return [line.split("\t") for line in result.stdout.splitlines() if line.strip()]


def test_all_six_tables_have_the_expected_columns_and_types():
    rows = run_sql_tsv("""
        select table_name, column_name, data_type, is_nullable
        from information_schema.columns
        where table_schema = 'public'
          and table_name in ('users', 'quizzes', 'questions', 'versions', 'submissions', 'answers')
        order by table_name, ordinal_position;
    """)
    actual: dict[str, dict[str, tuple[str, str]]] = {}
    for table_name, column_name, data_type, is_nullable in rows:
        actual.setdefault(table_name, {})[column_name] = (data_type, is_nullable)

    assert set(actual.keys()) == set(EXPECTED_COLUMNS.keys())
    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        assert (
            actual[table_name] == expected_columns
        ), f"{table_name} columns don't match CLAUDE.md Section 4"


def test_foreign_keys_match_spec():
    rows = run_sql_tsv("""
        select tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name, rc.delete_rule
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on tc.constraint_name = kcu.constraint_name
        join information_schema.constraint_column_usage ccu
          on tc.constraint_name = ccu.constraint_name
        join information_schema.referential_constraints rc
          on tc.constraint_name = rc.constraint_name
        where tc.constraint_type = 'FOREIGN KEY' and tc.table_schema = 'public'
        order by tc.table_name;
    """)
    actual = {
        (table, column): (ref_table, ref_column, delete_rule)
        for table, column, ref_table, ref_column, delete_rule in rows
    }
    assert actual == EXPECTED_FOREIGN_KEYS
