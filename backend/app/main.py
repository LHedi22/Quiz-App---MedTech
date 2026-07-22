from fastapi import FastAPI

from app.routers import excel

app = FastAPI(title="Exam Version Generator & Scanner")
app.include_router(excel.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
