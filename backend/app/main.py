from fastapi import FastAPI

from app.routers import excel, scan, versions

app = FastAPI(title="Exam Version Generator & Scanner")
app.include_router(excel.router)
app.include_router(versions.router)
app.include_router(scan.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
