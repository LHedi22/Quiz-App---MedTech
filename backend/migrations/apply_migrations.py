"""Applies every Phase 1 migration, in order, to $DATABASE_URL.

The single repeatable path used both to verify "applies cleanly with zero
manual intervention" against a fresh instance (Subtask 10.2) and, eventually,
against the real hosted production Supabase project once access to one
exists (see /docs/BLOCKERS.md). Plain psycopg rather than a `psql`
subprocess: this dev machine has no `psql` client installed, and psycopg is
already a runtime dependency this project's own code and test suite use for
every other direct-Postgres interaction (app/db.py, every backend/tests/
fixture) - one less external tool to require anywhere this script needs to
run, including inside CI.

Each file is sent as a single `cursor.execute()` call over one connection in
autocommit mode: psycopg3 uses the simple query protocol (which supports
multiple `;`-separated statements per call) whenever a query string is
executed with no bind parameters, and none of these migrations contain
`$$`-quoted function bodies whose internal semicolons could be
misinterpreted as statement boundaries (verified: `grep -c '\\$\\$'
migrations/*.sql` is 0 for all of them) - so this is safe for this specific
migration set, not a general-purpose SQL-file runner.

Usage: DATABASE_URL=postgresql://... python migrations/apply_migrations.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent

# Order matters: 0002 depends on 0001's tables existing, 0003 seeds data
# into tables 0001/0002 create and secure.
MIGRATION_FILES = [
    "0001_core_tables.up.sql",
    "0002_rls_policies.up.sql",
    "0003_seed_demo_data.sql",
]


def apply_migrations(database_url: str) -> None:
    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            for filename in MIGRATION_FILES:
                path = MIGRATIONS_DIR / filename
                sql = path.read_text(encoding="utf-8")
                print(f"Applying {filename} ...")
                cur.execute(sql)
    print("All migrations applied cleanly.")


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print(
            "DATABASE_URL must be set (e.g. the target Supabase project's "
            "Postgres connection string)",
            file=sys.stderr,
        )
        sys.exit(1)
    apply_migrations(database_url)


if __name__ == "__main__":
    main()
