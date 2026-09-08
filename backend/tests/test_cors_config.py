"""Web-app audit A3: CORS must not silently become all-or-nothing on one
env var. `configure_cors` warns when a deployed ENV has no configured
origin, folds in WEB_ORIGIN as a fallback, and still always allows
localhost for local dev.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import configure_cors

LOCAL_ORIGIN = "http://localhost:3000"
PROD_ORIGIN = "https://exam-scanner.vercel.app"


def _app_with_cors() -> FastAPI:
    app = FastAPI()
    configure_cors(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )


def test_warns_when_deployed_env_has_no_configured_origin(monkeypatch, caplog):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("WEB_ORIGIN", raising=False)

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        configure_cors(FastAPI())

    assert any("CORS" in r.message and "production" in r.message for r in caplog.records)


def test_no_warning_in_development(monkeypatch, caplog):
    monkeypatch.setenv("ENV", "development")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("WEB_ORIGIN", raising=False)

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        configure_cors(FastAPI())

    assert not any("CORS" in r.message for r in caplog.records)


def test_no_warning_in_deployed_env_when_allowed_origins_is_set(monkeypatch, caplog):
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("ALLOWED_ORIGINS", PROD_ORIGIN)
    monkeypatch.delenv("WEB_ORIGIN", raising=False)

    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        configure_cors(FastAPI())

    assert not any("CORS" in r.message for r in caplog.records)


def test_web_origin_is_accepted_as_a_fallback(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("WEB_ORIGIN", PROD_ORIGIN)

    client = TestClient(_app_with_cors())
    response = _preflight(client, PROD_ORIGIN)

    assert response.headers.get("access-control-allow-origin") == PROD_ORIGIN
    assert response.headers.get("access-control-max-age") == "600"


def test_configured_origin_gets_cors_headers_on_a_real_response(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", f"{PROD_ORIGIN}, https://other.example.com")

    client = TestClient(_app_with_cors())
    response = client.get("/health", headers={"Origin": PROD_ORIGIN})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == PROD_ORIGIN


def test_localhost_is_always_allowed_even_with_no_env(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("WEB_ORIGIN", raising=False)

    client = TestClient(_app_with_cors())
    response = client.get("/health", headers={"Origin": LOCAL_ORIGIN})

    assert response.headers.get("access-control-allow-origin") == LOCAL_ORIGIN


def test_an_unconfigured_origin_gets_no_cors_grant(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", PROD_ORIGIN)

    client = TestClient(_app_with_cors())
    response = _preflight(client, "https://evil.example.com")

    assert response.headers.get("access-control-allow-origin") is None
