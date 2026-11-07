"""Coordinator entry point. Room allocation will be implemented here."""
import os

from fastapi import FastAPI
from app.protocol import Health


app = FastAPI(title="dodgewuh coordinator", version="0.1.0")


@app.get("/api/health", response_model=Health)
def health() -> Health:
    return Health(build=os.getenv("BUILD_SHA", "dev"), rooms=0)
