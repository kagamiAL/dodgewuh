"""Gameplay constants — transcribed from plans/02-game-specification.md.

That document is the sole authority for every number here. Nothing else in this
package may hardcode a gameplay value: import from this module instead.

Frozen at contract commit 0a49de1.
"""

from __future__ import annotations

# --- Simulation clock -------------------------------------------------------
TICK_HZ: int = 60
DT: float = 1.0 / 60.0

# --- Court ------------------------------------------------------------------
# x in [-6, 6], z in [-9, 9] metres. y is visual height only and never enters
# any gameplay decision.
COURT_X: float = 6.0
COURT_Z: float = 9.0

# --- Bodies -----------------------------------------------------------------
CHAR_RADIUS: float = 0.45
BALL_RADIUS: float = 0.30  # bigger balls: easier hits (was 0.15)
# Swept-collision combined radius. 02 states 0.75 explicitly; it equals
# CHAR_RADIUS + BALL_RADIUS, but the specified value is what we use.
COMBINED_RADIUS: float = 0.75

# --- Character centre limits (team halves) ----------------------------------
# Team 1 occupies negative z, Team 2 positive z.
CHAR_X_LIMIT: float = 5.55
T1_Z_MIN: float = -8.55
T1_Z_MAX: float = -0.45
T2_Z_MIN: float = 0.45
T2_Z_MAX: float = 8.55

# --- Spawns -----------------------------------------------------------------
T1_SPAWN: tuple[float, float] = (0.0, -6.0)
T2_SPAWN: tuple[float, float] = (0.0, 6.0)

# --- Movement ---------------------------------------------------------------
MOVE_SPEED: float = 3.5
# Legs move vectors arrive with components in [-1, 1] and magnitude <= 1.001;
# slight excess is normalized rather than rejected (03 input.legs).
MOVE_MAGNITUDE_TOLERANCE: float = 1.001

# --- Balls ------------------------------------------------------------------
BALL_IDS: tuple[str, ...] = ("b1", "b2", "b3", "b4")
BALL_SPAWNS: dict[str, tuple[float, float]] = {
    "b1": (-2.0, -0.6),
    "b2": (2.0, -0.6),
    "b3": (-2.0, 0.6),
    "b4": (2.0, 0.6),
}

# --- Acquisition ------------------------------------------------------------
PICKUP_RANGE: float = 1.2  # centre-to-centre distance, inclusive

# --- No-throw zone ----------------------------------------------------------
# Release is illegal while abs(character centre z) <= 2.0. Inclusive boundary.
NO_THROW_ABS_Z: float = 2.0

# --- Throw ------------------------------------------------------------------
THROW_BASE_SPEED: float = 8.0
THROW_SPEED_PER_STRENGTH: float = 6.0
THROW_OFFSET: float = 0.65  # launch at centre + aim * THROW_OFFSET

# --- Flight and respawn -----------------------------------------------------
FLIGHT_TICKS: int = 120  # 2 seconds
RESPAWN_TICKS: int = 60  # 1 second
RESPAWN_MS: int = 1000

# --- Ballistic flight (amended rule; see 02 "Acquisition, hold, aim, release")
# A throw leaves the hands horizontally, because aim is a 2D {x,z} direction
# and the phone has no vertical-aim channel. Gravity then pulls the ball down,
# so the trajectory is the descending half of a parabola: flat at first, then
# drooping. The ball never rises, so it never leaves the vertical extent of a
# 1.8 m character, which is why the flat 2D swept-circle collision test stays
# exactly correct and is left untouched.
#
# Release height on a 1.8 m character: an overhand throw from shoulder level.
THROW_HEIGHT: float = 1.5
# A ball at rest sits on the floor, so its centre is one radius up.
GROUND_HEIGHT: float = BALL_RADIUS

# GRAVITY is a GAME-FEEL value, deliberately well below Earth's 9.81 m/s^2.
# It is the single dial for throw range, and the reason it is not 9.81:
#
#   fall time to the floor   t = sqrt(2 * (THROW_HEIGHT - GROUND_HEIGHT) / g)
#   horizontal range         r = speed * t,  speed = 8 + 6 * strength
#
#   g      t (s)   range @0.0   @0.5 (MVP)   @1.0
#   9.81   0.495    3.96 m       5.44 m       6.92 m
#   3.40   0.840    6.72 m       9.24 m      11.76 m
#
# The longest throw the court can require is 9.15 m: a thrower at the no-throw
# boundary (z = 2.0, launching at 1.35 after the 0.65 offset) against a
# defender hugging their own back wall (z = 8.55, whose hit surface is one
# COMBINED_RADIUS nearer at 7.80). At 9.81 a fixed-strength throw reaches only
# 5.44 m, so a defender who simply stands at their back wall cannot be hit at
# all and every round times out as a draw -- the "long draw chain" risk in
# plans/07. This value keeps the whole court reachable at the MVP's fixed
# strength 0.5 while still visibly arcing. Raise it for a steeper, shorter lob;
# lower it for a flatter, longer one.
#
# RECHECK THIS IF BALL_RADIUS, THROW_HEIGHT OR COMBINED_RADIUS CHANGES. The
# margin is only +0.09 m, and all three feed the arithmetic above: a bigger
# ball rests higher, which shortens the fall and so shortens every throw. That
# is exactly how 3.5 stopped working when BALL_RADIUS went 0.15 -> 0.30. The
# synthetic runner asserts the back-wall case, so it catches a regression.
GRAVITY: float = 3.4

# --- Round and phase timing -------------------------------------------------
ROUND_TICKS: int = 3600  # 60 seconds of active play
ROUND_MS: int = 60000
COUNTDOWN_TICKS: int = 180  # 3 seconds
RESULT_TICKS: int = 120  # 2 seconds

# --- Match ------------------------------------------------------------------
MATCH_POINTS: int = 2  # best of 3: first to 2 ends the match early
MAX_ROUNDS: int = 3  # otherwise the match ends after round 3; higher score wins, equal is a draw

# --- Input freshness --------------------------------------------------------
INPUT_TIMEOUT_MS: int = 250  # since the server received the last valid input

# --- Aim validation ---------------------------------------------------------
AIM_LENGTH_MIN: float = 0.99
AIM_LENGTH_MAX: float = 1.01
# Normalized aim must point into the opponent-facing hemisphere:
# T1 aim.z >= 0.2, T2 aim.z <= -0.2.
AIM_HEMISPHERE_MIN: float = 0.2

# --- Determinism ------------------------------------------------------------
# Two opposing hits within this time delta in the same tick are a draw.
SIMULTANEOUS_EPS: float = 1e-9

# --- Derived helpers --------------------------------------------------------
TEAMS: tuple[int, ...] = (1, 2)


def team_z_limits(team: int) -> tuple[float, float]:
    """Inclusive (min_z, max_z) for a team's character centre."""
    if team == 1:
        return (T1_Z_MIN, T1_Z_MAX)
    if team == 2:
        return (T2_Z_MIN, T2_Z_MAX)
    raise ValueError(f"unknown team {team!r}")


def team_spawn(team: int) -> tuple[float, float]:
    if team == 1:
        return T1_SPAWN
    if team == 2:
        return T2_SPAWN
    raise ValueError(f"unknown team {team!r}")


def team_forward_z(team: int) -> float:
    """T1 forward is +z, T2 forward is -z."""
    if team == 1:
        return 1.0
    if team == 2:
        return -1.0
    raise ValueError(f"unknown team {team!r}")


def opponent(team: int) -> int:
    if team == 1:
        return 2
    if team == 2:
        return 1
    raise ValueError(f"unknown team {team!r}")
