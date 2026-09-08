import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import excel, quizzes, scan, versions

logger = logging.getLogger("uvicorn.error")

_DEPLOYED_ENVS = {"staging", "production"}


def _configured_origins() -> list[str]:
    """Production origin(s) the browser is allowed to call from, on top of
    the localhost regex below. The Next.js web client runs on a different
    origin (`npm run dev` on localhost:3000 in dev; a Vercel domain in
    production). ALLOWED_ORIGINS (comma-separated) is the explicit list;
    WEB_ORIGIN (a single origin already set for other reasons) is folded in
    as a fallback so a missing ALLOWED_ORIGINS isn't automatically a total
    CORS outage. Never hardcoded - the hosting domain isn't known at
    code-write time."""
    raw = os.environ.get("ALLOWED_ORIGINS", "").split(",")
    web_origin = os.environ.get("WEB_ORIGIN", "").strip()
    if web_origin:
        raw.append(web_origin)
    # dict.fromkeys keeps insertion order while de-duplicating.
    return list(dict.fromkeys(o.strip() for o in raw if o.strip()))


def configure_cors(app: FastAPI) -> None:
    origins = _configured_origins()
    if not origins and os.environ.get("ENV", "development") in _DEPLOYED_ENVS:
        logger.warning(
            "CORS: neither ALLOWED_ORIGINS nor WEB_ORIGIN is set in ENV=%s - every "
            "cross-origin request from the web app (including the /health "
            "reachability ping that gates scanning) will fail preflight.",
            os.environ.get("ENV"),
        )
    app.add_middleware(
        CORSMiddleware,
        # Localhost/127.0.0.1 on any port is always allowed for local dev.
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
        # Let the browser cache a preflight result instead of re-OPTIONSing
        # every cross-origin call.
        max_age=600,
    )


app = FastAPI(title="Exam Version Generator & Scanner")
configure_cors(app)

app.include_router(excel.router)
app.include_router(versions.router)
app.include_router(scan.router)
app.include_router(quizzes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
