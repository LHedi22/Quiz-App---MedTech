from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import excel, quizzes, scan, versions

app = FastAPI(title="Exam Version Generator & Scanner")

# The Flutter web client runs on a different origin (flutter run -d chrome
# picks a random localhost port); CORS must be open for it to call this API
# at all. Scoped to localhost/127.0.0.1 (any port) rather than a wildcard,
# since this backend is dev-only for now (no production origin configured).
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
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
