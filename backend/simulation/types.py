"""Pure immutable DTOs for the authoritative simulation.

Field names mirror the wire schema in plans/03-api-contracts.md exactly, so
Alan's adapter maps these to Pydantic models field-for-field. Wire arrays become
tuples. Enum values stay the documented literal strings/integers.

Nothing in this module may import a framework: no Pydantic, FastAPI, websockets,
boto3 or asyncio. These are frozen dataclasses of tuples and scalars, which makes
every value returned by Simulation.snapshot() and Simulation.drain_events()
immutable by construction — networking cannot mutate simulation state.

Frozen at contract commit 0a49de1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

# --- Literal domains (mirror the TS/Pydantic enumerations in 03) ------------
Team = Literal[1, 2]
Role = Literal["arms", "legs"]
Phase = Literal["lobby", "countdown", "active", "round_end", "role_switch", "match_end"]
BallMode = Literal["ground", "held", "flying", "respawning"]
ResultReason = Literal["hit", "timeout", "simultaneous"]
ArmsAction = Literal["aim", "press", "release", "cancel"]


class SimulationError(Exception):
    """Synchronous rejection raised by Simulation methods.

    Carries one of the error codes listed in 03. A single rejection produces
    EITHER a raised SimulationError OR a deferred InputRejected event, never
    both.
    """

    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# --- Geometry ---------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Vec2:
    """World metres, or a normalized world direction. Wire shape {x, z}."""

    x: float
    z: float


# --- Room mapping -----------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Assignment:
    member_id: str
    team: Team
    role: Role


@dataclass(frozen=True, slots=True)
class Score:
    t1: int
    t2: int


# --- State records ----------------------------------------------------------
@dataclass(frozen=True, slots=True)
class CharacterDTO:
    team: Team
    pos: Vec2
    aim: Vec2
    held_ball_id: str | None
    # Cosmetic throwing-arm angle (degrees) echoed from the Arms phone; never used by gameplay.
    arm_pitch: float | None = None


@dataclass(frozen=True, slots=True)
class BallDTO:
    """One ball. `pos` and `velocity` are the gameplay plane; `height` is not.

    height is the ball centre's y in metres. It exists so screens draw the
    same arc from the same authority instead of each timing it locally, which
    01 requires of tick-matched state. It never enters a gameplay decision:
    collision is the flat 2D swept circle in [02].

    NOTE for the adapter: this field is additive and 03's `Ball` does not have
    it yet. See HANDOFF.md -- it needs the matching wire field before an
    `extra='forbid'` model will accept a converted snapshot.
    """

    ball_id: str
    mode: BallMode
    pos: Vec2
    velocity: Vec2
    owner_team: Team | None
    shooter_team: Team | None
    respawn_in_ms: int
    height: float


@dataclass(frozen=True, slots=True)
class ResultDTO:
    reason: ResultReason
    winner: Team | None
    hit_ball_id: str | None
    victim_team: Team | None


@dataclass(frozen=True, slots=True)
class StateDTO:
    """Full authoritative state. Equivalent to the wire `State` object.

    Invariants held by the engine, asserted by 03:
    - exactly two characters, sorted by team
    - exactly four balls, sorted by ball_id
    - tick is monotonic for the room lifetime and never resets
    - epoch never decreases
    - phase_remaining_ms is non-null only in countdown and round_end
    - winner is non-null only at match_end
    - owner_team is non-null only when held; shooter_team only when flying
    - non-flying velocity is zero; respawn_in_ms is zero unless respawning
    """

    tick: int
    epoch: int
    round: int
    phase: Phase
    remaining_ms: int
    phase_remaining_ms: int | None
    score: Score
    characters: tuple[CharacterDTO, ...]
    balls: tuple[BallDTO, ...]
    assignments: tuple[Assignment, ...]
    assignment_version: int
    result: ResultDTO | None
    winner: Team | None


# --- Inbound command DTOs ---------------------------------------------------
# These carry exactly the `Legs` / `Arms` wire payload fields and no identity:
# the authenticated member is the `member_id` argument to apply_input, and team
# and role are derived from the simulation's own assignment mapping.
@dataclass(frozen=True, slots=True)
class LegsCommand:
    seq: int
    epoch: int
    move: Vec2


@dataclass(frozen=True, slots=True)
class ArmsCommand:
    seq: int
    epoch: int
    aim: Vec2
    action: ArmsAction
    strength: float | None
    # Cosmetic throwing-arm angle (degrees) for the screen animation; optional.
    arm_pitch: float | None = None


Command = Union[LegsCommand, ArmsCommand]


# --- Outbound events --------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PhaseChanged:
    """A phase boundary. Adapter maps to the `phase.changed` envelope."""

    state: StateDTO


@dataclass(frozen=True, slots=True)
class RolesChanged:
    """Assignment mapping after a simulation swap. Maps to `roles.changed`."""

    assignments: tuple[Assignment, ...]
    assignment_version: int
    epoch: int


@dataclass(frozen=True, slots=True)
class InputRejected:
    """Deferred, targeted rejection. Adapter maps to the `error` envelope.

    ref_seq echoes the rejected command's seq. The only deferred rejection in
    this engine is NO_THROW_ZONE; every other rejection raises SimulationError
    from apply_input instead.
    """

    member_id: str
    code: str
    message: str
    ref_seq: int | None


SimEvent = Union[PhaseChanged, RolesChanged, InputRejected]


__all__ = [
    "ArmsAction",
    "ArmsCommand",
    "Assignment",
    "BallDTO",
    "BallMode",
    "CharacterDTO",
    "Command",
    "InputRejected",
    "LegsCommand",
    "Phase",
    "PhaseChanged",
    "ResultDTO",
    "ResultReason",
    "Role",
    "RolesChanged",
    "Score",
    "SimEvent",
    "SimulationError",
    "StateDTO",
    "Team",
    "Vec2",
]
