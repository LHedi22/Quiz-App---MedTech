from fastapi import FastAPI

from app.routers import excel, versions

app = FastAPI(title="Exam Version Generator & Scanner")
app.include_router(excel.router)
app.include_router(versions.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
