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
# x in [-7.8, 7.8], z in [-9, 9] metres (playtest: 30% wider, same length). y is
# visual height only and never enters any gameplay decision.
COURT_X: float = 7.8
COURT_Z: float = 9.0

# --- Bodies -----------------------------------------------------------------
CHAR_RADIUS: float = 0.45
BALL_RADIUS: float = 0.30  # bigger balls: easier hits (was 0.15)
# Swept-collision combined radius. 02 states 0.75 explicitly; it equals
# CHAR_RADIUS + BALL_RADIUS, but the specified value is what we use.
COMBINED_RADIUS: float = 0.75

# --- Character centre limits (team halves) ----------------------------------
# Team 1 occupies negative z, Team 2 positive z.
CHAR_X_LIMIT: float = 7.35  # COURT_X - CHAR_RADIUS
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
# Three per side (playtest; was two). b1-b3 on Team 1's side, b4-b6 on Team 2's.
BALL_IDS: tuple[str, ...] = ("b1", "b2", "b3", "b4", "b5", "b6")
BALL_SPAWNS: dict[str, tuple[float, float]] = {
    "b1": (-3.0, -0.6),
    "b2": (0.0, -0.6),
    "b3": (3.0, -0.6),
    "b4": (-3.0, 0.6),
    "b5": (0.0, 0.6),
    "b6": (3.0, 0.6),
}

# --- Acquisition ------------------------------------------------------------
PICKUP_RANGE: float = 1.2  # centre-to-centre distance, inclusive

# --- No-throw zone ----------------------------------------------------------
# Release is illegal while abs(character centre z) <= 2.0. Inclusive boundary.
NO_THROW_ABS_Z: float = 2.0

# --- Throw ------------------------------------------------------------------
# Three throw levels from the phone (weak 0 / medium 0.5 / hard 1): see GRAVITY for ranges.
THROW_BASE_SPEED: float = 12.0  # was 8.0
THROW_SPEED_PER_STRENGTH: float = 8.0  # was 6.0 (then 7.0 before the court widened): 12 / 16 / 20 m/s
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
#   horizontal range         r = speed * t,  speed = 12 + 7 * strength
#
#   g      t (s)   weak @0.0   medium @0.5   hard @1.0
#   3.40   0.840   10.08 m     13.02 m       15.96 m
#   1.90   1.124   13.49 m     17.98 m       22.48 m   <- current (12 + 8 * strength)
#
# PLAYTEST AMENDMENT: the phone sends three levels. A weak throw carries about
# 75% of the 18 m court; a hard throw clears the worst case -- corner to corner,
# a thrower in their own back corner (launch z -7.90 after the offset) against a
# defender in the far back corner (hit surface z 7.80), 2 x CHAR_X_LIMIT apart
# in x -- about 21.5 m on the widened court -- with some to spare. The release stays horizontal, so the ball
# only ever drops (1.2 m over its flight): a throw, never a lob over anyone.
#
# Original rationale, kept for history:
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
GRAVITY: float = 1.9  # was 3.4; see the playtest amendment above

# --- Round and phase timing -------------------------------------------------
ROUND_TICKS: int = 3600  # 60 seconds of active play
ROUND_MS: int = 60000
COUNTDOWN_TICKS: int = 180  # 3 seconds
# Lobby auto-start hold: all four must stay ready this long before the countdown
# begins. Unlike an abort, a cancelled hold costs nobody their calibration.
LOBBY_START_TICKS: int = 120  # 2 seconds
RESULT_TICKS: int = 120  # 2 seconds

# --- Match ------------------------------------------------------------------
MATCH_POINTS: int = 2  # best of 3: first to 2 ends the match early
MAX_ROUNDS: int = 3  # otherwise the match ends after round 3; higher score wins, equal is a draw

# --- Camera dodge -----------------------------------------------------------
# A ball that actually hits a victim whose team has a screen camera (and isn't
# thrown at their back) starts a dodge instead of ending the round: the ball is
# held at the victim, the worker slows the room to 1 step per SLOWMO_FACTOR real
# ticks, the victim freezes, and the victim's camera screen reports whether the
# player physically stepped out of an overlaid ball (dodged: play goes on) or
# not (hit: they lose the round).
# Tick counts below are SIMULATION ticks; real time is SLOWMO_FACTOR times longer.
SLOWMO_FACTOR: int = 8
DODGE_VERDICT_TIMEOUT_TICKS: int = 15  # 2 s real: no verdict by then is a hit (window is 1.1 s)
# No dodge for a ball thrown at your back: its direction of travel within 45 degrees of the way
# the victim's camera sees them face (dot product above cos 45).
DODGE_BACK_DOT: float = 0.7071
DODGE_SLOWMO_TICKS: int = 45  # slow motion lasts this long (6 s real) once a verdict exists

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
