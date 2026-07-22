from fastapi import FastAPI

app = FastAPI(title="Exam Version Generator & Scanner")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
