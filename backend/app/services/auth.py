"""Verifies Supabase-issued JWTs and resolves the requesting professor.

The web app authenticates directly against Supabase Auth and sends the
resulting access token as a Bearer token on every backend request. The
backend never talks to Supabase Auth itself for this - it only needs to
verify the token's signature and read the `sub`/`email` claims, per
CLAUDE.md's "trusted backend" pattern already used by `app/db.py`.

Discovery: this project's local Supabase stack issues ES256-signed tokens
via its JWKS endpoint (the newer Supabase "signing keys" feature), not the
legacy shared-secret HS256 `JWT_SECRET` — verified by inspecting a real
token's header and confirming `/auth/v1/.well-known/jwks.json` serves a
matching EC key. Verification below fetches that JWKS (via `PyJWKClient`,
which caches keys and re-fetches on an unrecognized `kid`), so it also works
unmodified against a real hosted Supabase project.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID

import jwt
import psycopg
from fastapi import Header, HTTPException

SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54341")
JWT_AUDIENCE = "authenticated"

_jwks_client = jwt.PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json")


@dataclass
class AuthUser:
    id: UUID
    email: str | None


def _decode_token(token: str) -> AuthUser:
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience=JWT_AUDIENCE,
            # Small leeway tolerates clock skew between this process and the
            # Dockerized Supabase Auth container that mints `iat`/`exp` -
            # observed intermittently in a repeated-request stress test as
            # `ImmatureSignatureError` with zero leeway.
            leeway=10,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc

    return AuthUser(id=UUID(payload["sub"]), email=payload.get("email"))


def get_current_user(authorization: str = Header(...)) -> AuthUser:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    return _decode_token(token)


def ensure_user_row(conn: psycopg.Connection, user: AuthUser) -> None:
    """Upserts the professor into `public.users` on first authenticated call.

    `public.users` is a separate table from Supabase's own `auth.users`
    (see CLAUDE.md Section 4); rows are created lazily here rather than via
    a signup-time trigger, since no such trigger exists yet.

    Uses an explicit `conn.commit()` rather than `with conn:` - the latter
    closes the underlying connection (not just the transaction) once this
    function returns, per the same psycopg3 gotcha already documented in
    PROGRESS.md for Phase 6.4's `apply_manual_correction`, and callers here
    always keep using `conn` afterwards.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into users (id, email)
            values (%s, %s)
            on conflict (id) do update set email = excluded.email
            """,
            (user.id, user.email or ""),
        )
    conn.commit()
