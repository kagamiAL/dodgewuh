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
BALL_RADIUS: float = 0.15
# Swept-collision combined radius. 02 states 0.60 explicitly; it equals
# CHAR_RADIUS + BALL_RADIUS, but the specified value is what we use.
COMBINED_RADIUS: float = 0.60

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

# --- Round and phase timing -------------------------------------------------
ROUND_TICKS: int = 3600  # 60 seconds of active play
ROUND_MS: int = 60000
COUNTDOWN_TICKS: int = 180  # 3 seconds
RESULT_TICKS: int = 120  # 2 seconds

# --- Match ------------------------------------------------------------------
MATCH_POINTS: int = 3  # first to 3; draws award no point; no round cap

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
