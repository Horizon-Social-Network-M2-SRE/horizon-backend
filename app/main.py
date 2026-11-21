from fastapi import FastAPI

app = FastAPI(title="Horizon Backend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
