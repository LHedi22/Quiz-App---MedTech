"""Supabase Storage client for version PDFs.

Talks to the Storage REST API directly over HTTP with the service-role key
(same trusted-backend model as `app/db.py`), rather than pulling in the full
supabase-py SDK for one bucket's worth of operations.
"""

from __future__ import annotations

import os
from uuid import UUID

import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54341")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0."
    "EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU",
)
BUCKET = "version-pdfs"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
    }


def _url(path: str) -> str:
    return f"{SUPABASE_URL}/storage/v1{path}"


def object_path(quiz_id: UUID, version_id: UUID) -> str:
    return f"{quiz_id}/{version_id}.pdf"


def ensure_bucket() -> None:
    """Create the bucket if it doesn't exist yet. Safe to call repeatedly."""
    resp = httpx.post(
        _url("/bucket"),
        headers=_headers(),
        json={"id": BUCKET, "name": BUCKET, "public": False},
        timeout=10,
    )
    if resp.status_code in (200, 201):
        return
    if resp.status_code == 400 and "already exists" in resp.text.lower():
        return
    if resp.status_code == 409:
        return
    resp.raise_for_status()


def object_exists(path: str) -> bool:
    resp = httpx.get(_url(f"/object/info/{BUCKET}/{path}"), headers=_headers(), timeout=10)
    return resp.status_code == 200


def upload_pdf(path: str, pdf_bytes: bytes) -> None:
    resp = httpx.post(
        _url(f"/object/{BUCKET}/{path}"),
        headers={
            **_headers(),
            "Content-Type": "application/pdf",
            "x-upsert": "true",
        },
        content=pdf_bytes,
        timeout=30,
    )
    resp.raise_for_status()


def download_pdf(path: str) -> bytes:
    resp = httpx.get(_url(f"/object/{BUCKET}/{path}"), headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.content


def create_signed_url(path: str, expires_in: int = 3600) -> str:
    resp = httpx.post(
        _url(f"/object/sign/{BUCKET}/{path}"),
        headers=_headers(),
        json={"expiresIn": expires_in},
        timeout=10,
    )
    resp.raise_for_status()
    signed_path = resp.json()["signedURL"]
    return f"{SUPABASE_URL}/storage/v1{signed_path}"
