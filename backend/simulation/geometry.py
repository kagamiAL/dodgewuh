"""Pure 2D vector maths, clamps, collision and input validation.

Standard library only. Holds the vector helpers, half-court clamps, the
move/aim validators, and the relative-motion swept-circle solver and court-exit
clip used by ball flight.
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


# --- Flight clipping and swept collision ------------------------------------
# Both helpers below are parametrized by the SAME quantity: u, the fraction of
# one tick, 0.0 at tick start and 1.0 at tick end. Keeping one shared time base
# is what lets a ball be clipped to a wall endpoint while the character still
# moves across the whole tick, without the two segments drifting apart.
def wall_exit_fraction(pos: Vec2, disp: Vec2) -> float | None:
    """Tick fraction at which a ball centre leaves the court, or None.

    Court exit is the ball CENTRE leaving the rectangle, the decision recorded
    on in_court(). 02 specifies no bounce, so the first boundary crossing on
    either axis ends the flight. None means the ball stays inside for the whole
    tick. A ball that somehow starts outside returns 0.0 rather than a negative
    fraction.
    """
    earliest: float | None = None
    for p, d, limit in ((pos.x, disp.x, K.COURT_X), (pos.z, disp.z, K.COURT_Z)):
        if d > 0.0:
            u = (limit - p) / d
        elif d < 0.0:
            u = (-limit - p) / d
        else:
            continue  # no motion on this axis, so it cannot cross either side
        if u < 0.0:
            u = 0.0
        if u <= 1.0 and (earliest is None or u < earliest):
            earliest = u
    return earliest


def ground_impact_fraction(
    height: float,
    vertical_velocity: float,
    floor: float = K.GROUND_HEIGHT,
    gravity: float = K.GRAVITY,
) -> float | None:
    """Tick fraction at which a falling ball's centre reaches the floor.

    None means it is still airborne at the end of the tick. Solves the exact
    parabola rather than stepping it, so the landing point does not depend on
    tick granularity:

        floor = height + vy*t - g*t^2/2   ->   (g/2)t^2 - vy*t - drop = 0

    A ball already at or below the floor returns 0.0.
    """
    drop = height - floor
    if drop <= 0.0:
        return 0.0
    if gravity <= 0.0:
        return None  # no gravity configured, so it never comes down

    disc = vertical_velocity * vertical_velocity + 2.0 * gravity * drop
    if disc < 0.0:  # unreachable for drop > 0 and gravity > 0
        return None
    seconds = (vertical_velocity + math.sqrt(disc)) / gravity
    if seconds < 0.0:
        return None
    fraction = seconds / K.DT
    if fraction > 1.0:
        return None
    return fraction


def fall(
    height: float,
    vertical_velocity: float,
    seconds: float,
    gravity: float = K.GRAVITY,
) -> tuple[float, float]:
    """Advance a ballistic height and vertical velocity by `seconds`.

    Closed form for constant acceleration, so there is no Euler drift and the
    published height is the true parabola at every tick.
    """
    new_height = (
        height + vertical_velocity * seconds - 0.5 * gravity * seconds * seconds
    )
    return new_height, vertical_velocity - gravity * seconds


def swept_hit(
    ball_pos: Vec2,
    ball_disp: Vec2,
    char_from: Vec2,
    char_to: Vec2,
    limit: float = 1.0,
) -> float | None:
    """Earliest tick fraction in [0, limit] where a flying ball touches a
    moving character, or None if it never does within that window.

    Relative-motion swept circles with the combined radius from 02 (0.75 m):
    the ball's segment is swept against the character's movement segment, which
    is what prevents tunnelling at high speed. `limit` is the ball's clipped
    wall/lifetime endpoint for this tick; 02 says a hit at or before that
    endpoint counts, so u == limit is a hit.

    ball_disp is the ball's displacement over the WHOLE tick, not the clipped
    part: clipping is expressed through `limit` so that both segments stay on
    the same time base.
    """
    if limit < 0.0:
        return None

    d0 = sub(ball_pos, char_from)
    # Relative displacement per tick: ball motion minus character motion.
    w = sub(ball_disp, sub(char_to, char_from))
    radius = K.COMBINED_RADIUS

    # |d0 + w*u| = radius  ->  a*u^2 + b*u + c = 0
    c = dot(d0, d0) - radius * radius
    if c <= 0.0:
        return 0.0  # already touching at tick start
    a = dot(w, w)
    if a == 0.0:
        return None  # no relative motion, and not already touching
    b = 2.0 * dot(d0, w)
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return None  # closest approach never reaches the combined radius

    u = (-b - math.sqrt(disc)) / (2.0 * a)
    # c > 0 means both roots carry the same sign, so a negative entry root puts
    # the whole crossing before this tick: nothing to resolve now.
    if u < 0.0 or u > limit:
        return None
    return u


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
