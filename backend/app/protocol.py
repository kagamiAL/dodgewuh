"""Shared wire models, implemented from plans/03-api-contracts.md."""
from typing import Literal

from pydantic import BaseModel


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    build: str
    rooms: int
