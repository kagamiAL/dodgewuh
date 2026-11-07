"""Wire models from plan 03; gameplay messages follow in the socket slice."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Trim before checking length, and reject non-string names rather than coercing them.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=24, strict=True)]


class CreateRoom(Model):
    name: Name


class JoinRoom(CreateRoom):
    device: Literal["screen", "phone"]


class Registration(Model):
    """One-time credential response; ws_path is reserved for the transport slice."""
    room_id: str
    room_code: str
    member_id: str
    token: str
    ws_path: str


class RestError(Model):
    code: str
    message: str


class Health(Model):
    status: Literal["ok"] = "ok"
    build: str
    rooms: Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
