"""Pure 2D vector maths, clamps and input validation. Standard library only.

The swept-circle collision solver is added in M4; this module currently holds
the vector helpers, half-court clamps and the move/aim validators needed by
movement and snapshots.
"""

from __future__ import annotations

import math

from . import constants as K
from .types import SimulationError, Vec2

ZERO = Vec2(0.0, 0.0)


# --- Vector helpers ---------------------------------------------------------
def add(a: Vec2, b: Vec2) -> Vec2:
    return Vec2(a.x + b.x, a.z + b.z)


def sub(a: Vec2, b: Vec2) -> Vec2:
    return Vec2(a.x - b.x, a.z - b.z)


def scale(v: Vec2, k: float) -> Vec2:
    return Vec2(v.x * k, v.z * k)


def dot(a: Vec2, b: Vec2) -> float:
    return a.x * b.x + a.z * b.z


def length(v: Vec2) -> float:
    return math.hypot(v.x, v.z)


def distance(a: Vec2, b: Vec2) -> float:
    return math.hypot(a.x - b.x, a.z - b.z)


def normalize(v: Vec2) -> Vec2:
    """Unit vector. Returns ZERO for a zero-length input."""
    n = math.hypot(v.x, v.z)
    if n == 0.0:
        return ZERO
    return Vec2(v.x / n, v.z / n)


def is_finite(v: Vec2) -> bool:
    return math.isfinite(v.x) and math.isfinite(v.z)


def team_forward(team: int) -> Vec2:
    """Default aim: straight forward. T1 is +z, T2 is -z."""
    return Vec2(0.0, K.team_forward_z(team))


# --- Clamps -----------------------------------------------------------------
def clamp(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def clamp_to_half(pos: Vec2, team: int) -> Vec2:
    """Clamp a character centre into its own half, per 02 centre limits."""
    z_min, z_max = K.team_z_limits(team)
    return Vec2(
        clamp(pos.x, -K.CHAR_X_LIMIT, K.CHAR_X_LIMIT),
        clamp(pos.z, z_min, z_max),
    )


def in_court(pos: Vec2) -> bool:
    """True while a ball centre is inside the court rectangle.

    Documented decision: court exit is the ball CENTRE leaving the rectangle.
    02 says court exit triggers respawn but specifies no radius inset, so the
    centre is used and recorded rather than silently choosing an inset.
    """
    return -K.COURT_X <= pos.x <= K.COURT_X and -K.COURT_Z <= pos.z <= K.COURT_Z


# --- Input validation -------------------------------------------------------
def validate_move(move: Vec2) -> Vec2:
    """Validate a Legs move vector and return it normalized if slightly long.

    03 input.legs: components in [-1, 1], vector magnitude <= 1.001, normalize
    slight excess. 02: diagonal magnitude is capped at 1, so a (1, 1) input
    yields speed 3.5 m/s, not 4.95.
    """
    if not is_finite(move):
        raise SimulationError("INVALID_INPUT", "move must be finite")
    if not (-1.0 <= move.x <= 1.0) or not (-1.0 <= move.z <= 1.0):
        raise SimulationError("INVALID_INPUT", "move components must be within [-1, 1]")
    n = length(move)
    if n > K.MOVE_MAGNITUDE_TOLERANCE:
        raise SimulationError("INVALID_INPUT", "move magnitude must be <= 1.001")
    if n > 1.0:
        return normalize(move)
    return move


def validate_aim(aim: Vec2, team: int) -> Vec2:
    """Validate and normalize an aim vector for a team.

    03: length bounds first, normalize, THEN check the opponent-facing
    hemisphere. Rejects zero and backward aim.
    """
    if not is_finite(aim):
        raise SimulationError("INVALID_INPUT", "aim must be finite")
    n = length(aim)
    if not (K.AIM_LENGTH_MIN <= n <= K.AIM_LENGTH_MAX):
        raise SimulationError(
            "INVALID_INPUT",
            f"aim length must be within [{K.AIM_LENGTH_MIN}, {K.AIM_LENGTH_MAX}]",
        )
    unit = normalize(aim)
    forward_z = K.team_forward_z(team)
    if unit.z * forward_z < K.AIM_HEMISPHERE_MIN:
        raise SimulationError(
            "INVALID_INPUT", "aim must point into the opponent-facing hemisphere"
        )
    return unit
