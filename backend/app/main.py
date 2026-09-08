import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import excel, quizzes, scan, versions

app = FastAPI(title="Exam Version Generator & Scanner")

# The Next.js web client runs on a different origin (`npm run dev` on
# localhost:3000 in dev; a Vercel domain in production). Localhost/127.0.0.1
# (any port) is always allowed for local dev; ALLOWED_ORIGINS
# (comma-separated, e.g. "https://exam-scanner.vercel.app") adds production
# origin(s) on top - set via Cloud Run env vars, never hardcoded, since the
# hosting domain isn't known at code-write time.
_extra_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_origins=_extra_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(excel.router)
app.include_router(versions.router)
app.include_router(scan.router)
app.include_router(quizzes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
