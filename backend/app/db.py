import os

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:54342/postgres",
)


def get_connection() -> psycopg.Connection:
    """Open a direct Postgres connection using the service credential.

    Bypasses RLS by design: the backend is a trusted intermediary that will
    enforce professor ownership at the API layer once auth is wired in
    (later phase), not by relying on RLS for its own writes.
    """
    return psycopg.connect(DATABASE_URL)
