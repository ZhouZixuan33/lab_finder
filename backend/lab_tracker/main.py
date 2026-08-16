"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(title="Lab Application Tracker", version="0.1.0")


@app.get("/api/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Return a lightweight process-health response."""

    return {"status": "ok"}
