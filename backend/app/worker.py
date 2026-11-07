"""Worker entry point. Richard's simulation will run in this process."""
import os

from fastapi import FastAPI

from app.protocol import Health

app = FastAPI(title="dodgewuh game worker", version="0.1.0")


@app.get("/api/health", response_model=Health)
def health() -> Health:
    return Health(build=os.getenv("BUILD_SHA", "dev"), rooms=0)
