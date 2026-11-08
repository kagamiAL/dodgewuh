"""The authoritative gameplay simulation.

Implements the `Simulation` seam specified in plans/03-api-contracts.md. Every
method is synchronous and socket-free. No FastAPI, Pydantic, WebSocket, AWS or
PlayCanvas import appears anywhere in this package.

All eight seam methods carry their final production signatures so Alan
integrates once and never rebases on a signature change. Live now: lobby/reset
state, full snapshot projection, apply_input validation with room-wide ordinal
defense, fixed-step movement with half-court clamps and stale-input stop, Hold
acquisition and ownership, safe cancel and the no-throw zone, constant-speed
flight with relative-motion swept collision, wall/expiry respawn and
earliest-hit resolution, ballistic arcs that land and stay where they land, and
the complete lifecycle: exactly-once scoring, the
3600-tick timeout draw, lobby -> countdown -> active -> round_end ->
role_switch -> countdown ... -> match_end, every-round role swapping, readiness
gating of the next round, best-of-3 match end, reset/abort/rematch to lobby, and the
simulation-owned device guard that aborts a non-lobby phase when a required
device is lost.

Every ordered task in plans/agents/richard.md through task 8 is implemented.
Remaining work is task 9: running the full synthetic match as a diagnostic and
then the real four-phone integration, neither of which adds engine mechanics.

INTEGRATION NOTE for the adapter. The device guard decides only from the facts
passed to set_readiness, and it is evaluated once per step() before any phase
work. 03 fixes the boundaries at which readiness is cleared: swap, reset, abort
and rematch -- NOT the countdown or active transition. If readiness facts are
cleared when entering countdown or active, this guard will abort every match on
its next step, because a phone cannot legally send ready=true outside
lobby/role_switch and so can never recover. Keep the facts across countdown and
active.

Frozen at contract commit 0a49de1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from . import constants as K
from . import geometry as G
from .types import (
    ArmsCommand,
    Assignment,
    BallDTO,
    CharacterDTO,
    Command,
    DodgeDTO,
    DodgeOutcome,
    InputRejected,
    LegsCommand,
    Phase,
    PhaseChanged,
    ResultDTO,
    RolesChanged,
    Score,
    SimEvent,
    SimulationError,
    StateDTO,
    Vec2,
)

CANONICAL_SLOTS: tuple[tuple[int, str], ...] = (
    (1, "arms"),
    (1, "legs"),
    (2, "arms"),
    (2, "legs"),
)

ControlAction = Literal["start", "reset", "rematch", "abort"]


# --- Mutable internal records (never handed out; snapshot() projects to DTOs)
@dataclass(slots=True)
class _Character:
    team: int
    pos: Vec2
    aim: Vec2
    held_ball_id: str | None = None


@dataclass(slots=True)
class _Ball:
    ball_id: str
    mode: str
    pos: Vec2
    velocity: Vec2
    owner_team: int | None = None
    shooter_team: int | None = None
    respawn_ticks: int = 0
    flight_ticks: int = 0
    # Ballistic height state. Cosmetic for gameplay (collision is flat 2D) but
    # authoritative, so every screen draws the same arc.
    height: float = K.GROUND_HEIGHT
    vertical_velocity: float = 0.0


@dataclass(slots=True)
class _LegsInput:
    move: Vec2
    received_ms: int | None


@dataclass(slots=True)
class _ArmsState:
    hold: bool
    aim: Vec2
    received_ms: int | None
    # Cosmetic arm angle from the phone, echoed in snapshots for the throw animation only.
    arm_pitch: float | None = None


@dataclass(frozen=True, slots=True)
class _FlightPlan:
    """One flying ball's resolved tick: where it ends and why it stops there.

    `limit` is the fraction of the tick actually travelled after clipping to
    the floor, a wall or the lifetime endpoint. `ending` is None while the ball
    stays airborne, 'ground' when it touches down, 'wall' when it leaves the
    court. `hit_at` is the swept-circle impact fraction, or None.
    """

    ball_id: str
    endpoint: Vec2
    limit: float
    ending: str | None
    hit_at: float | None


@dataclass(slots=True)
class _Dodge:
    """The one camera dodge in progress. `team` is the victim; `ticks` counts
    simulation steps since it began."""

    ball_id: str
    team: int
    outcome: DodgeOutcome = "pending"
    ticks: int = 0


@dataclass(frozen=True, slots=True)
class _Pending:
    member_id: str
    team: int
    role: str
    command: Command
    received_ms: int
    ordinal: int


class Simulation:
    """One room's authoritative gameplay state."""

    def __init__(self, assignments: tuple[Assignment, ...] = ()) -> None:
        validated = self._validate_assignments(tuple(assignments))

        self._phase: Phase = "lobby"
        self._tick: int = 0
        self._epoch: int = 0
        self._round: int = 0
        self._score: dict[int, int] = {1: 0, 2: 0}
        self._active_ticks: int = 0
        self._phase_ticks_left: int | None = None
        self._assignments: tuple[Assignment, ...] = validated
        self._assignment_version: int = 1 if validated else 0
        self._result: ResultDTO | None = None
        self._winner: int | None = None

        self._characters: dict[int, _Character] = {}
        self._balls: dict[str, _Ball] = {}
        self._reset_arena()

        self._pending: list[_Pending] = []
        self._last_ordinal: int = 0
        self._legs_input: dict[int, _LegsInput] = {
            team: _LegsInput(G.ZERO, None) for team in K.TEAMS
        }
        self._arms: dict[int, _ArmsState] = {
            team: _ArmsState(False, G.team_forward(team), None) for team in K.TEAMS
        }

        self._ready_ids: frozenset[str] = frozenset()
        self._connected_ids: frozenset[str] = frozenset()
        self._screen_count: int = 0
        self._host_connected: bool = False

        # Camera dodge: teams whose screen camera can judge a dodge, the dodge in
        # progress, and balls their victim already dodged (they can no longer hit).
        self._dodge_teams: frozenset[int] = frozenset()
        # team -> (unit world facing from its camera, received_ms); stale after K.INPUT_TIMEOUT_MS.
        self._facing: dict[int, tuple[Vec2, int]] = {}
        self._now_ms: int = 0
        self._dodge: _Dodge | None = None
        self._dodged_balls: set[str] = set()

        self._events: list[SimEvent] = []

    # --- Seam: assignments --------------------------------------------------
    def set_assignments(self, assignments: tuple[Assignment, ...]) -> None:
        """Lobby only. Adapter supplies slot membership.

        Empty slots are filled by the missing team/role pair in canonical slot
        order, preserving existing lobby assignments. assignment_version
        increments only when the mapping actually changes. A lobby assignment
        change invalidates all readiness.
        """
        if self._phase != "lobby":
            raise SimulationError(
                "INVALID_PHASE", "assignments may only be set in lobby"
            )
        supplied = self._validate_assignments(tuple(assignments))

        slots: dict[tuple[int, str], str] = {
            (a.team, a.role): a.member_id for a in supplied
        }
        # The adapter supplies the complete live membership mapping. Omitted
        # members have released their seats; retaining them prevents expiry/leave.
        merged = tuple(
            Assignment(member_id=slots[slot], team=slot[0], role=slot[1])  # type: ignore[arg-type]
            for slot in CANONICAL_SLOTS
            if slot in slots
        )
        if merged == self._assignments:
            return

        self._assignments = merged
        self._assignment_version += 1
        self._ready_ids = frozenset()
        self._events.append(
            RolesChanged(
                assignments=self._assignments,
                assignment_version=self._assignment_version,
                epoch=self._epoch,
            )
        )

    # --- Seam: readiness facts ---------------------------------------------
    def set_readiness(
        self,
        ready_member_ids: frozenset[str],
        connected_member_ids: frozenset[str],
        screen_count: int,
        host_connected: bool,
    ) -> None:
        """Record adapter-supplied facts only. Decides nothing.

        Every readiness, abort and role_switch -> countdown decision is taken on
        the next step(), giving one decision point and no duplicate aborts.
        """
        if screen_count < 0:
            raise SimulationError("INVALID_INPUT", "screen_count must be >= 0")
        self._ready_ids = frozenset(ready_member_ids)
        self._connected_ids = frozenset(connected_member_ids)
        self._screen_count = int(screen_count)
        self._host_connected = bool(host_connected)

    # --- Seam: camera dodge -------------------------------------------------
    def set_dodge_teams(self, teams: frozenset[int]) -> None:
        """Adapter fact: teams whose Legs a screen camera watches. Only they can
        dodge; a team without a camera is hit exactly as before."""
        self._dodge_teams = frozenset(t for t in teams if t in K.TEAMS)

    def set_facing(self, team: int, facing: Vec2, received_ms: int) -> None:
        """Adapter fact: which way the team's Legs player faces, as its screen
        camera sees it (zero when nobody is tracked). Only the dodge reads it."""
        if team in K.TEAMS:
            self._facing[team] = (G.normalize(facing), received_ms)

    def resolve_dodge(self, team: int, ball_id: str, epoch: int, dodged: bool) -> None:
        """The victim's camera screen reports the pending dodge's verdict."""
        if self._phase != "active":
            raise SimulationError("INVALID_PHASE", "no dodge outside active")
        if epoch != self._epoch:
            raise SimulationError("STALE_EPOCH", "dodge verdict carries a stale epoch")
        d = self._dodge
        if d is None or d.outcome != "pending" or d.team != team or d.ball_id != ball_id:
            raise SimulationError("NOT_PENDING", "no matching dodge is pending")
        d.outcome = "dodged" if dodged else "hit"
        if dodged:
            self._dodged_balls.add(ball_id)

    @property
    def slow_motion(self) -> bool:
        """True while a dodge runs; the adapter then steps once per K.SLOWMO_FACTOR ticks."""
        return self._dodge is not None

    # --- Seam: host/transport control --------------------------------------
    def control(self, action: ControlAction, reason: str | None = None) -> None:
        """Adapter authorizes host actions; simulation validates phase."""
        if action == "start":
            self._control_start()
        elif action == "reset":
            self._reset_to_lobby()
        elif action == "abort":
            self._reset_to_lobby()
        elif action == "rematch":
            if self._phase != "match_end":
                raise SimulationError(
                    "INVALID_PHASE", "rematch is only valid at match_end"
                )
            self._reset_to_lobby()
        else:
            raise SimulationError("INVALID_INPUT", f"unknown action {action!r}")

    def _control_start(self) -> None:
        if self._phase != "lobby":
            raise SimulationError("INVALID_PHASE", "start is only valid in lobby")
        if len(self._assignments) != 4:
            raise SimulationError("NOT_READY", "four assigned phones are required")
        if self._screen_count < 1:
            raise SimulationError("NOT_READY", "at least one screen must be connected")
        if not self._host_connected:
            # Without this the device guard would abort the match on its first
            # step, since 02 makes an original-host disconnect an immediate
            # reset. Refusing here is the same rule, applied earlier.
            raise SimulationError("NOT_READY", "the original host must be connected")
        for a in self._assignments:
            if a.member_id not in self._connected_ids:
                raise SimulationError("NOT_READY", f"{a.member_id} is not connected")
            if a.member_id not in self._ready_ids:
                raise SimulationError("NOT_READY", f"{a.member_id} is not ready")

        # 02: reset scores on start. _enter_countdown increments the round, so
        # the first round of a match comes out as round 1.
        self._score = {1: 0, 2: 0}
        self._result = None
        self._winner = None
        self._round = 0
        self._enter_countdown()

    # --- Seam: input --------------------------------------------------------
    def apply_input(
        self,
        member_id: str,
        command: Command,
        received_ms: int,
        ordinal: int,
    ) -> None:
        """Validate and enqueue one command for the next step.

        Synchronous rejections raise SimulationError. The only deferred
        rejection in this engine is NO_THROW_ZONE (M3), emitted as an
        InputRejected event from step(). Never both for one rejection.

        Duplicate defense uses the room-wide receive ordinal, not a member
        seq counter, so a reconnected phone's seq=1 is accepted.
        """
        if not isinstance(member_id, str) or not member_id:
            raise SimulationError("UNAUTHORIZED", "member_id is required")
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
            raise SimulationError("INVALID_INPUT", "ordinal must be a nonnegative int")
        if (
            isinstance(received_ms, bool)
            or not isinstance(received_ms, int)
            or received_ms < 0
        ):
            raise SimulationError(
                "INVALID_INPUT", "received_ms must be a nonnegative int"
            )
        if ordinal <= self._last_ordinal:
            raise SimulationError("OLD_SEQ", "ordinal is not newer than the last one")

        assignment = next(
            (a for a in self._assignments if a.member_id == member_id), None
        )
        if assignment is None:
            raise SimulationError("WRONG_ROLE", "member holds no current assignment")

        if isinstance(command, LegsCommand):
            expected_role = "legs"
        elif isinstance(command, ArmsCommand):
            expected_role = "arms"
        else:
            raise SimulationError("INVALID_INPUT", "unknown command type")
        if assignment.role != expected_role:
            raise SimulationError(
                "WRONG_ROLE", f"member is {assignment.role}, not {expected_role}"
            )

        if self._phase != "active":
            raise SimulationError("INVALID_PHASE", "gameplay input requires active")
        if command.epoch != self._epoch:
            raise SimulationError("STALE_EPOCH", "command carries a stale epoch")
        if (
            isinstance(command.seq, bool)
            or not isinstance(command.seq, int)
            or command.seq < 0
        ):
            raise SimulationError("INVALID_INPUT", "seq must be a nonnegative int")

        if isinstance(command, LegsCommand):
            G.validate_move(command.move)
        else:
            G.validate_aim(command.aim, assignment.team)
            if command.action == "release":
                s = command.strength
                if isinstance(s, bool) or not isinstance(s, (int, float)):
                    raise SimulationError(
                        "INVALID_INPUT", "release requires a numeric strength"
                    )
                if not math.isfinite(s) or not (0.0 <= s <= 1.0):
                    raise SimulationError(
                        "INVALID_INPUT", "strength must be within [0, 1]"
                    )
            elif command.strength is not None:
                raise SimulationError(
                    "INVALID_INPUT", "strength is only allowed on release"
                )
            pitch = command.arm_pitch
            if pitch is not None and (
                isinstance(pitch, bool)
                or not isinstance(pitch, (int, float))
                or not math.isfinite(pitch)
                or not -360.0 <= pitch <= 360.0
            ):
                raise SimulationError("INVALID_INPUT", "arm_pitch must be finite degrees")

        self._last_ordinal = ordinal
        self._pending.append(
            _Pending(
                member_id=member_id,
                team=assignment.team,
                role=assignment.role,
                command=command,
                received_ms=received_ms,
                ordinal=ordinal,
            )
        )

    # --- Seam: fixed step ---------------------------------------------------
    def step(self, now_ms: int) -> None:
        """Exactly one fixed step. now_ms is used only for stale input checks.

        The active clock is tick-based, never wall-clock. tick advances once per
        step in every phase and never resets.
        """
        if isinstance(now_ms, bool) or not isinstance(now_ms, int):
            raise SimulationError("INVALID_INPUT", "now_ms must be an int")

        self._tick += 1

        # (0) Simulation-owned device guard, evaluated once per step before any
        # phase work. 03 reserves this single decision point for step() so a
        # required-device loss cannot produce a duplicate abort from socket
        # cleanup, and 02 requires the reset to happen immediately.
        if self._abort_trigger() is not None:
            # 03: the simulation implements abort as a complete reset to lobby.
            # It deliberately does NOT score or swap roles: 02 says the old
            # round awards no point and triggers no swap, because it was
            # aborted rather than completed.
            self._reset_to_lobby()
            return

        phase = self._phase

        if phase == "active":
            self._step_active(now_ms)
        elif phase == "countdown":
            # Countdown ignores all gameplay input.
            self._pending.clear()
            if self._phase_ticks_left is not None:
                self._phase_ticks_left -= 1
                if self._phase_ticks_left <= 0:
                    self._enter_active()
        elif phase == "round_end":
            # Hold the result visible for 2 seconds, then swap roles.
            self._pending.clear()
            if self._phase_ticks_left is not None:
                self._phase_ticks_left -= 1
                if self._phase_ticks_left <= 0:
                    self._enter_role_switch()
        elif phase == "lobby":
            # Auto-start after a short hold, so a phone that blips right after
            # readying cancels the start here instead of aborting the countdown
            # (which would send every phone back to recalibrate). The hold
            # restarts from full whenever anyone stops being ready.
            self._pending.clear()
            if not self._ready_to_begin():
                self._phase_ticks_left = None
            else:
                if self._phase_ticks_left is None:
                    self._phase_ticks_left = K.LOBBY_START_TICKS
                self._phase_ticks_left -= 1
                if self._phase_ticks_left <= 0:
                    self._control_start()
        elif phase == "role_switch":
            # Wait here indefinitely. 02: never force-start an unready
            # controller. 03: this decision is taken on the step after
            # set_readiness, which is the engine's single decision point.
            self._pending.clear()
            if self._ready_to_begin():
                self._enter_countdown()
        else:
            # match_end holds. The tick still advances, which is what
            # 03 requires of every phase.
            self._pending.clear()

    def _step_active(self, now_ms: int) -> None:
        self._now_ms = now_ms
        # (1) At tick start, if the round's 3600 active ticks have elapsed, end
        # a timeout draw BEFORE accepting throws. This is what makes a throw
        # arriving at the deadline ineligible while a hit in the last valid
        # step still counts.
        if self._active_ticks >= K.ROUND_TICKS:
            self._pending.clear()
            self._finish_round(
                ResultDTO(
                    reason="timeout", winner=None, hit_ball_id=None, victim_team=None
                )
            )
            return

        pending = sorted(self._pending, key=lambda p: p.ordinal)
        self._pending = []

        # (2) latest valid Legs move per team; preserve every Arms edge in order.
        latest_legs: dict[int, _Pending] = {}
        arms_edges: list[_Pending] = []
        for p in pending:
            if isinstance(p.command, LegsCommand):
                latest_legs[p.team] = p
            else:
                arms_edges.append(p)

        for team, p in latest_legs.items():
            assert isinstance(p.command, LegsCommand)
            self._legs_input[team] = _LegsInput(
                G.validate_move(p.command.move), p.received_ms
            )
        for p in arms_edges:
            self._arms[p.team].received_ms = p.received_ms

        # (3) clear stale controls, then move and clamp.
        for team in K.TEAMS:
            legs = self._legs_input[team]
            if legs.received_ms is None or now_ms - legs.received_ms > K.INPUT_TIMEOUT_MS:
                legs.move = G.ZERO
            arms = self._arms[team]
            if arms.received_ms is None or now_ms - arms.received_ms > K.INPUT_TIMEOUT_MS:
                arms.arm_pitch = None
                if arms.hold:
                    arms.hold = False
                    self._drop_held(team)

        # The swept collision in (5) needs each character's movement segment
        # for this tick, so remember where they started before moving them.
        prev_pos = {team: self._characters[team].pos for team in K.TEAMS}
        # A dodge victim stands still until they dodge: their camera, not their
        # Legs jog, decides whether the ball connects.
        frozen = (
            self._dodge.team
            if self._dodge is not None and self._dodge.outcome != "dodged"
            else None
        )
        for team in K.TEAMS:
            char = self._characters[team]
            move = self._legs_input[team].move
            if team != frozen and (move.x or move.z):
                char.pos = G.clamp_to_half(
                    G.add(char.pos, G.scale(move, K.MOVE_SPEED * K.DT)), team
                )

        # (4a) Retry previously latched holds in team-number order at the NEW
        # positions, before any edge in this tick is replayed (02 step 4).
        for team in K.TEAMS:
            if self._arms[team].hold:
                self._try_acquire(team)

        # (4b) Replay Arms edges in receive-ordinal order. Edges are never
        # collapsed into a final button value, so press+release in one tick
        # works, a later aim cannot redirect an earlier release, and a cancel
        # cannot undo an already-legal throw.
        for p in arms_edges:
            cmd = p.command
            assert isinstance(cmd, ArmsCommand)
            team = p.team
            arms = self._arms[team]
            # Aim was validated and normalized in apply_input; normalize again
            # so the stored aim is always a unit vector.
            aim = G.validate_aim(cmd.aim, team)
            arms.aim = aim
            self._characters[team].aim = aim
            if cmd.arm_pitch is not None:
                arms.arm_pitch = float(cmd.arm_pitch)

            if cmd.action == "press":
                arms.hold = True
                self._try_acquire(team)
            elif cmd.action == "release":
                # Uses its own aim and the possession as it stands right now.
                self._release(team, aim, cmd.strength, p.member_id, cmd.seq)
                arms.hold = False
            elif cmd.action == "cancel":
                self._drop_held(team)
                arms.hold = False
            # 'aim' updates aim only, which happened above.

        # Held balls follow their character.
        self._sync_held_balls()

        # (4c) Camera dodge: a ball about to hit a still, camera-watched victim
        # starts slow motion before it connects.
        if self._dodge is None:
            self._detect_dodge()

        # (5) Advance flight, resolve the earliest valid hit, then respawns.
        decided = self._step_flight(prev_pos)

        # (6) The tick ran, so it counts, including the tick a hit lands in.
        self._active_ticks += 1
        if decided is not None:
            # A hit ends the round immediately.
            self._finish_round(decided)
            return
        self._advance_dodge()

    # --- Internal: camera dodge ---------------------------------------------
    def _detect_dodge(self) -> None:
        """Start a dodge for the first flying ball (by ID) within
        K.DODGE_TRIGGER_DISTANCE of its victim that would really hit them
        (judged as if they stopped where they are), moving or not -- unless the
        ball is coming at their back. With no
        fresh camera facing the dodge is allowed. This runs every tick, so
        turning to face a ball still starts the dodge."""
        for ball_id in K.BALL_IDS:
            ball = self._balls[ball_id]
            if ball.mode != "flying" or ball_id in self._dodged_balls:
                continue
            victim = K.opponent(ball.shooter_team)  # type: ignore[arg-type]
            if victim not in self._dodge_teams:
                continue
            if G.distance(ball.pos, self._characters[victim].pos) > K.DODGE_TRIGGER_DISTANCE:
                continue  # still too far away
            if self._at_back(ball, victim):
                continue  # thrown at their back: no chance to dodge
            if self._ticks_to_contact(ball, self._characters[victim].pos) is not None:
                self._dodge = _Dodge(ball_id=ball_id, team=victim)
                return

    def _at_back(self, ball: _Ball, victim: int) -> bool:
        """Is the ball travelling the way the victim faces, i.e. into their back?"""
        seen = self._facing.get(victim)
        if seen is None or self._now_ms - seen[1] > K.INPUT_TIMEOUT_MS:
            return False
        facing = seen[0]
        if not (facing.x or facing.z):
            return False
        return G.dot(G.normalize(ball.velocity), facing) > K.DODGE_BACK_DOT

    @staticmethod
    def _ticks_to_contact(ball: _Ball, victim: Vec2) -> int | None:
        """Ticks until `ball` reaches a victim standing at `victim`, or None if
        it lands, leaves the court or expires first or is further off than the
        dodge lead. Replays _step_flight's clipping on a copy of the ball."""
        pos, height, vv = ball.pos, ball.height, ball.vertical_velocity
        disp = G.scale(ball.velocity, K.DT)
        remaining = min(K.DODGE_LEAD_TICKS, K.FLIGHT_TICKS - ball.flight_ticks)
        for n in range(remaining):
            exit_at = G.wall_exit_fraction(pos, disp)
            land_at = G.ground_impact_fraction(height, vv)
            limit = 1.0
            if exit_at is not None:
                limit = exit_at
            if land_at is not None and land_at < limit:
                limit = land_at
            if G.swept_hit(pos, disp, victim, victim, limit) is not None:
                return n
            if limit < 1.0:
                return None
            pos = G.add(pos, disp)
            height, vv = G.fall(height, vv, K.DT)
        return None

    def _advance_dodge(self) -> None:
        """Count the dodge's ticks: no verdict in time is a hit; once decided,
        slow motion ends after K.DODGE_SLOWMO_TICKS or when its ball stops flying."""
        d = self._dodge
        if d is None:
            return
        d.ticks += 1
        if d.outcome == "pending":
            if d.ticks >= K.DODGE_VERDICT_TIMEOUT_TICKS:
                d.outcome = "hit"
            return
        if d.ticks >= K.DODGE_SLOWMO_TICKS or self._balls[d.ball_id].mode != "flying":
            self._dodge = None

    # --- Internal: acquisition and release ----------------------------------
    def _try_acquire(self, team: int) -> None:
        """Acquire the nearest grounded ball in range, ties broken by ball ID.

        One held ball per character, and no ball can be acquired twice: only
        grounded balls are candidates, so a ball already held by anyone is
        never eligible.
        """
        char = self._characters[team]
        if char.held_ball_id is not None:
            return

        best_id: str | None = None
        best_distance = 0.0
        for ball_id in sorted(self._balls):  # ball ID order breaks equal ties
            ball = self._balls[ball_id]
            if ball.mode != "ground":
                continue
            distance = G.distance(char.pos, ball.pos)
            if distance > K.PICKUP_RANGE:  # inclusive boundary
                continue
            if best_id is None or distance < best_distance:
                best_id, best_distance = ball_id, distance

        if best_id is None:
            return
        ball = self._balls[best_id]
        ball.mode = "held"
        ball.owner_team = team
        ball.shooter_team = None
        ball.velocity = G.ZERO
        ball.respawn_ticks = 0
        ball.flight_ticks = 0
        ball.pos = char.pos
        # Carried at the height it will be released from.
        ball.height = K.THROW_HEIGHT
        ball.vertical_velocity = 0.0
        char.held_ball_id = best_id

    def _release(
        self,
        team: int,
        aim: Vec2,
        strength: float | None,
        member_id: str,
        ref_seq: int,
    ) -> None:
        """Resolve a release edge. Hold is cleared by the caller either way."""
        char = self._characters[team]
        if char.held_ball_id is None:
            # Releasing without a ball clears Hold and has no gameplay effect.
            return

        if abs(char.pos.z) <= K.NO_THROW_ABS_Z:
            # Safe cancellation: drop grounded at the character centre and tell
            # the phone why. This is the only deferred rejection in the engine.
            self._drop_held(team)
            self._events.append(
                InputRejected(
                    member_id=member_id,
                    code="NO_THROW_ZONE",
                    message="Move back before throwing",
                    ref_seq=ref_seq,
                )
            )
            return

        ball = self._balls[char.held_ball_id]
        speed = K.THROW_BASE_SPEED + K.THROW_SPEED_PER_STRENGTH * float(strength or 0.0)
        ball.mode = "flying"
        ball.pos = G.add(char.pos, G.scale(aim, K.THROW_OFFSET))
        ball.velocity = G.scale(aim, speed)
        ball.owner_team = None
        ball.shooter_team = team  # only the opposing character can be hit
        ball.flight_ticks = 0
        ball.respawn_ticks = 0
        # The throw itself is unchanged: aim is a 2D direction and there is no
        # vertical-aim channel, so the ball leaves the hands horizontally and
        # gravity takes over from there.
        ball.height = K.THROW_HEIGHT
        ball.vertical_velocity = 0.0
        char.held_ball_id = None

    def _sync_held_balls(self) -> None:
        for team in K.TEAMS:
            held = self._characters[team].held_ball_id
            if held is not None:
                self._balls[held].pos = self._characters[team].pos

    # --- Internal: flight, collision and respawn ----------------------------
    def _step_flight(self, prev_pos: dict[int, Vec2]) -> ResultDTO | None:
        """02 step 5: advance flight, resolve the earliest valid hit, respawns.

        Returns the round's outcome if one connected this tick, else None. The
        caller owns the consequences (scoring and the round_end transition), so
        this stays a pure physics step.

        Flight is ballistic: horizontal velocity never changes, while gravity
        pulls the ball down from its release height. There is no bounce, and
        height never enters a collision decision -- a horizontally released
        ball cannot rise, so it stays inside a 1.8 m character's vertical
        extent for its whole flight and the flat 2D swept circle remains
        exactly right. Each ball is clipped to the earliest of its floor, wall
        and lifetime endpoint BEFORE the hit test, and a hit at or before that
        endpoint counts.

        Only a flying ball can hit, and only the character opposing its shooter:
        grounded, held and respawning balls damage nobody, and because the test
        is ball-against-character only, a held ball can never block a throw.
        """
        # Balls already respawning when the tick began. A ball that starts
        # respawning during THIS tick must not also be counted down in it, or
        # the delay would come out one tick short of the specified second.
        already_respawning = [
            ball_id
            for ball_id in K.BALL_IDS
            if self._balls[ball_id].mode == "respawning"
        ]

        # --- Advance each flying ball and collect its hit candidate.
        # K.BALL_IDS is a fixed tuple, so iteration order is stable by ball ID.
        plans: list[_FlightPlan] = []
        for ball_id in K.BALL_IDS:
            ball = self._balls[ball_id]
            if ball.mode != "flying":
                continue

            disp = G.scale(ball.velocity, K.DT)

            # Clip the tick to the earliest of: hitting the floor, crossing a
            # wall, or running out of lifetime. The hit test then runs over
            # that same window, so a hit at or before the endpoint counts.
            exit_at = G.wall_exit_fraction(ball.pos, disp)
            land_at = G.ground_impact_fraction(ball.height, ball.vertical_velocity)
            limit = 1.0
            ending: str | None = None
            if exit_at is not None:
                limit, ending = exit_at, "wall"
            if land_at is not None and land_at < limit:
                # A tie goes to the wall: a ball touching down exactly as it
                # leaves the court must not come to rest outside it.
                limit, ending = land_at, "ground"

            endpoint = G.add(ball.pos, G.scale(disp, limit))

            # _release is the only writer of mode='flying' and always records a
            # shooter team, so the opponent lookup below is always defined.
            victim = K.opponent(ball.shooter_team)  # type: ignore[arg-type]
            hit_at = (
                None  # dodged: it flies straight through its victim
                if ball_id in self._dodged_balls
                else G.swept_hit(
                    ball.pos,
                    disp,
                    prev_pos[victim],
                    self._characters[victim].pos,
                    limit,
                )
            )
            d = self._dodge
            if (
                hit_at is not None
                and d is not None
                and d.ball_id == ball_id
                and d.outcome == "pending"
            ):
                # Awaiting the camera verdict: park the ball just short of the
                # victim. It neither connects, falls nor ages until decided.
                parked = max(0.0, hit_at - 1e-6)
                endpoint = G.add(ball.pos, G.scale(disp, parked))
                plans.append(_FlightPlan(ball_id, endpoint, 0.0, None, None))
                continue
            plans.append(_FlightPlan(ball_id, endpoint, limit, ending, hit_at))

        for plan in plans:
            ball = self._balls[plan.ball_id]
            ball.pos = plan.endpoint
            if plan.limit == 0.0 and plan.ending is None:
                continue  # parked for a dodge verdict
            ball.height, ball.vertical_velocity = G.fall(
                ball.height, ball.vertical_velocity, K.DT * plan.limit
            )
            ball.flight_ticks += 1

        # --- Earliest valid hit. Ties use ball ID; opposing hits within 1e-9
        # of each other are a draw awarding no point.
        decided = self._resolve_hit(plans)
        if decided is not None:
            # The round ended inside this tick, so no respawn starts or runs:
            # role_switch resets the arena anyway. The hit ball stays flying
            # where the advance left it, matching the round_end example in 03.
            return decided

        # --- Endpoint consequences.
        # Touching down leaves the ball lying where it landed; leaving the
        # court or running out of lifetime respawns it.
        for plan in plans:
            ball = self._balls[plan.ball_id]
            if plan.ending == "ground":
                self._land(ball)
            elif plan.ending == "wall" or ball.flight_ticks >= K.FLIGHT_TICKS:
                self._begin_respawn(ball)
            if ball.mode != "flying":
                self._dodged_balls.discard(plan.ball_id)

        # --- Then respawns, per the step order in 02.
        for ball_id in already_respawning:
            ball = self._balls[ball_id]
            ball.respawn_ticks -= 1
            if ball.respawn_ticks <= 0:
                ball.respawn_ticks = 0
                ball.mode = "ground"
                spawn_x, spawn_z = K.BALL_SPAWNS[ball_id]
                ball.pos = Vec2(spawn_x, spawn_z)
                ball.height = K.GROUND_HEIGHT
                ball.vertical_velocity = 0.0

        return None

    def _resolve_hit(self, plans: list[_FlightPlan]) -> ResultDTO | None:
        """Pick the one outcome this tick, or None if nothing connected.

        02: compute the earliest time of impact in the tick, break equal times
        by ball ID, and award a draw with no points if two OPPOSING hits land
        within 1e-9 of each other. Later candidates are ignored outright.
        """
        candidates = [
            (plan.hit_at, plan.ball_id) for plan in plans if plan.hit_at is not None
        ]
        if not candidates:
            return None

        earliest = min(hit_at for hit_at, _ in candidates)
        tied = [
            ball_id
            for hit_at, ball_id in candidates
            if hit_at - earliest <= K.SIMULTANEOUS_EPS
        ]
        victims = {
            K.opponent(self._balls[ball_id].shooter_team)  # type: ignore[arg-type]
            for ball_id in tied
        }
        if len(victims) > 1:
            # Two opposing hits at the same instant: nobody scores.
            return ResultDTO(
                reason="simultaneous", winner=None, hit_ball_id=None, victim_team=None
            )

        ball_id = min(tied)  # equal times break by ball ID
        shooter = self._balls[ball_id].shooter_team
        return ResultDTO(
            reason="hit",
            winner=shooter,  # type: ignore[arg-type]
            hit_ball_id=ball_id,
            victim_team=K.opponent(shooter),  # type: ignore[arg-type]
        )

    def _land(self, ball: _Ball) -> None:
        """A thrown ball touches down and stays there. No bounce, no roll.

        It becomes an ordinary grounded ball at the point of impact, so it
        damages nobody and can be picked up again by whoever reaches it. This
        is the amended ballistic rule: a ball that runs out of height is no
        longer respawned, it is simply lying on the court.
        """
        ball.mode = "ground"
        ball.velocity = G.ZERO
        ball.owner_team = None
        ball.shooter_team = None
        ball.height = K.GROUND_HEIGHT
        ball.vertical_velocity = 0.0
        ball.flight_ticks = 0
        ball.respawn_ticks = 0

    def _begin_respawn(self, ball: _Ball) -> None:
        """Start the 1 second respawn at this ball's own original spawn.

        The ball is parked at its spawn for the whole delay. 02 specifies the
        delay and the spawn but not an intermediate position, and a respawning
        ball damages nobody, so showing it where it will reappear is recorded
        here rather than silently choosing somewhere else.
        """
        spawn_x, spawn_z = K.BALL_SPAWNS[ball.ball_id]
        ball.mode = "respawning"
        ball.pos = Vec2(spawn_x, spawn_z)
        ball.velocity = G.ZERO
        ball.owner_team = None
        ball.shooter_team = None
        ball.respawn_ticks = K.RESPAWN_TICKS
        ball.flight_ticks = 0
        ball.height = K.GROUND_HEIGHT
        ball.vertical_velocity = 0.0

    # --- Seam: snapshot -----------------------------------------------------
    def snapshot(self) -> StateDTO:
        """Full immutable state. Frozen dataclasses of tuples all the way down."""
        characters = tuple(
            CharacterDTO(
                team=team,  # type: ignore[arg-type]
                pos=self._characters[team].pos,
                aim=self._characters[team].aim,
                held_ball_id=self._characters[team].held_ball_id,
                arm_pitch=self._arms[team].arm_pitch,
            )
            for team in sorted(self._characters)
        )
        balls = tuple(
            BallDTO(
                ball_id=b.ball_id,
                mode=b.mode,  # type: ignore[arg-type]
                pos=b.pos,
                velocity=b.velocity if b.mode == "flying" else G.ZERO,
                owner_team=b.owner_team if b.mode == "held" else None,  # type: ignore[arg-type]
                shooter_team=b.shooter_team if b.mode == "flying" else None,  # type: ignore[arg-type]
                respawn_in_ms=(
                    self._ticks_to_ms(b.respawn_ticks) if b.mode == "respawning" else 0
                ),
                height=b.height,
            )
            for b in (self._balls[bid] for bid in sorted(self._balls))
        )
        return StateDTO(
            tick=self._tick,
            epoch=self._epoch,
            round=self._round,
            phase=self._phase,
            remaining_ms=self._remaining_ms(),
            phase_remaining_ms=self._phase_remaining_ms(),
            score=Score(t1=self._score[1], t2=self._score[2]),
            characters=characters,
            balls=balls,
            assignments=self._assignments,
            assignment_version=self._assignment_version,
            result=self._result,
            winner=self._winner,  # type: ignore[arg-type]
            dodge=(
                DodgeDTO(
                    ball_id=self._dodge.ball_id,
                    team=self._dodge.team,  # type: ignore[arg-type]
                    outcome=self._dodge.outcome,
                )
                if self._dodge is not None
                else None
            ),
        )

    # --- Seam: events -------------------------------------------------------
    def drain_events(self) -> list[SimEvent]:
        """Ordered events since the last drain. Exactly-once."""
        events = self._events
        self._events = []
        return events

    # --- Internal: phases ---------------------------------------------------
    def _enter_countdown(self) -> None:
        """Begin a round: reset arena and timer, bump the round number.

        02: the next countdown begins with reset balls/characters/timer and an
        incremented round number, and the previous result clears here. 03:
        result persists through round_end and role_switch, clears at the next
        countdown.
        """
        self._active_ticks = 0
        self._result = None
        self._round += 1
        self._reset_arena()
        self._transition("countdown", K.COUNTDOWN_TICKS)

    def _enter_active(self) -> None:
        # Fresh movement is allowed on active entry, but Hold starts false.
        self._transition("active", None)

    def _finish_round(self, result: ResultDTO) -> None:
        """Score the round exactly once, then show the result.

        This is the ONLY place a point is awarded. It is reached once per round
        because it immediately moves the phase out of active, and _step_active
        only runs while active — so a round cannot be scored twice.

        02: a hit awards one point; timeout or simultaneous hit awards none.
        """
        self._result = result
        if result.reason == "hit" and result.winner is not None:
            self._score[result.winner] += 1
        # 02: enter round_end and keep the result visible for 2 seconds. The
        # arena is deliberately NOT reset here — that happens on entering
        # role_switch, so the deciding ball stays where players can see it.
        self._transition("round_end", K.RESULT_TICKS)

    def _enter_role_switch(self) -> None:
        """Reset the arena, swap roles, then either end the match or wait.

        02: reset arena on entering role_switch; swap the two phone IDs within
        each team after EVERY round, including draws and the winning round;
        increment assignment version and clear all readiness. Best of 3: if a
        team reached MATCH_POINTS, or MAX_ROUNDS rounds have been played, enter
        match_end after the swap.
        """
        self._reset_arena()
        self._swap_roles()
        self._transition("role_switch", None)
        # 03: on a phase/role transition, phase.changed then roles.changed.
        self._events.append(
            RolesChanged(
                assignments=self._assignments,
                assignment_version=self._assignment_version,
                epoch=self._epoch,
            )
        )
        if max(self._score.values()) >= K.MATCH_POINTS or self._round >= K.MAX_ROUNDS:
            self._enter_match_end()

    def _enter_match_end(self) -> None:
        """Best of 3. The winner and the final result are retained here.

        The higher score wins; an equal score after MAX_ROUNDS is a draw, so
        winner stays None (the wire allows a null winner at match_end).

        02: match_end displays winner and final score, and calibration is not
        required again until rematch. 03: winner is non-null only at match_end,
        and match_end retains the final result.
        """
        t1, t2 = self._score[1], self._score[2]
        self._winner = 1 if t1 > t2 else 2 if t2 > t1 else None
        self._ready_ids = frozenset()
        self._transition("match_end", None)

    def _swap_roles(self) -> None:
        """Swap Arms and Legs within each team, keeping teams intact.

        Teammates trade roles; nobody changes team. assignment_version
        increments and all readiness clears, so every phone must recalibrate
        and explicitly ready again before the next round.
        """
        by_slot = {(a.team, a.role): a.member_id for a in self._assignments}
        swapped: list[Assignment] = []
        for team, role in CANONICAL_SLOTS:
            partner = "legs" if role == "arms" else "arms"
            member_id = by_slot.get((team, partner))
            if member_id is None:
                continue
            swapped.append(
                Assignment(member_id=member_id, team=team, role=role)  # type: ignore[arg-type]
            )
        self._assignments = tuple(swapped)
        self._assignment_version += 1
        self._ready_ids = frozenset()

    def _ready_to_begin(self) -> bool:
        """Gate for starting a round: four connected ready phones and a screen.

        02: role_switch waits for all four phones to recalibrate and explicitly
        become ready, with at least one screen, and never force-starts an
        unready controller. The host must be connected too, otherwise the
        device guard below would abort the round on its very first step.
        """
        if len(self._assignments) != 4 or self._screen_count < 1:
            return False
        if not self._host_connected:
            return False
        return all(
            a.member_id in self._connected_ids and a.member_id in self._ready_ids
            for a in self._assignments
        )

    def _abort_trigger(self) -> str | None:
        """Why the current phase must abort to lobby, or None to carry on.

        This is the simulation-owned device guard. It decides only from the
        facts the adapter supplied through set_readiness; it never inspects a
        socket. 02 interruptions:

        - a phone disconnect, the original host disconnecting, or the loss of
          ALL screens, in any non-lobby phase, resets the match immediately;
        - a current-epoch phone going ready=false during countdown or active
          does the same;
        - in any other phase a ready=false only clears that member's
          readiness, which needs no action here because readiness is just a
          fact set and role_switch simply keeps waiting;
        - losing one screen while another remains is a membership change only,
          so the test is "no screens left", not "fewer screens".

        Returns a short machine-readable trigger for diagnostics. It is NOT
        published: StateDTO has no abort-reason field and inventing one would
        be contract drift, so the adapter owns the user-facing message. It
        already knows which device vanished.
        """
        if self._phase == "lobby":
            return None

        for a in self._assignments:
            if a.member_id not in self._connected_ids:
                return "phone_disconnected"
        if not self._host_connected:
            return "host_disconnected"
        if self._screen_count < 1:
            return "all_screens_lost"

        if self._phase in ("countdown", "active"):
            for a in self._assignments:
                if a.member_id not in self._ready_ids:
                    return "readiness_revoked"
        return None

    def _reset_to_lobby(self) -> None:
        """Complete reset to lobby. Also the implementation of abort.

        A reset while already in lobby still increments epoch and emits
        PhaseChanged(lobby), so stale readiness or input cannot restart it.
        Assignments are retained; score, controls, held balls, timer and
        readiness are cleared.
        """
        self._score = {1: 0, 2: 0}
        self._round = 0
        self._active_ticks = 0
        self._result = None
        self._winner = None
        self._ready_ids = frozenset()
        self._reset_arena()
        self._transition("lobby", None)

    def _transition(self, phase: Phase, phase_ticks: int | None) -> None:
        """Every phase transition clears latched controls and bumps epoch.

        It also ends any camera dodge: slow motion never outlives the phase."""
        self._dodge = None
        self._dodged_balls.clear()
        self._phase = phase
        self._phase_ticks_left = phase_ticks
        self._epoch += 1
        self._clear_controls()
        self._events.append(PhaseChanged(state=self.snapshot()))

    def _clear_controls(self) -> None:
        """Clear latched controls. A role change or phase transition drops the
        held ball without velocity or damage, same as cancel or stale input."""
        self._pending.clear()
        for team in K.TEAMS:
            self._drop_held(team)
            self._legs_input[team] = _LegsInput(G.ZERO, None)
            self._arms[team] = _ArmsState(False, G.team_forward(team), None)

    # --- Internal: arena ----------------------------------------------------
    def _reset_arena(self) -> None:
        self._characters = {}
        for team in K.TEAMS:
            sx, sz = K.team_spawn(team)
            self._characters[team] = _Character(
                team=team,
                pos=Vec2(sx, sz),
                aim=G.team_forward(team),
                held_ball_id=None,
            )
        self._balls = {}
        for ball_id in K.BALL_IDS:
            bx, bz = K.BALL_SPAWNS[ball_id]
            self._balls[ball_id] = _Ball(
                ball_id=ball_id,
                mode="ground",
                pos=Vec2(bx, bz),
                velocity=G.ZERO,
            )

    def _drop_held(self, team: int) -> None:
        """Drop without velocity or damage, grounded at the character centre."""
        char = self._characters[team]
        ball_id = char.held_ball_id
        if ball_id is None:
            return
        ball = self._balls[ball_id]
        ball.mode = "ground"
        ball.pos = char.pos
        ball.velocity = G.ZERO
        ball.owner_team = None
        ball.shooter_team = None
        # Dropped, not thrown: it is on the floor, with no velocity of any kind.
        ball.height = K.GROUND_HEIGHT
        ball.vertical_velocity = 0.0
        char.held_ball_id = None

    # --- Internal: clocks ---------------------------------------------------
    @staticmethod
    def _ticks_to_ms(ticks: int) -> int:
        """03: timed phase milliseconds use ceil(remaining_ticks * 1000 / 60)."""
        if ticks <= 0:
            return 0
        return -(-ticks * 1000 // K.TICK_HZ)

    def _remaining_ms(self) -> int:
        remaining = K.ROUND_TICKS - self._active_ticks
        if remaining >= K.ROUND_TICKS:
            return K.ROUND_MS
        return self._ticks_to_ms(remaining)

    def _phase_remaining_ms(self) -> int | None:
        """Non-null in countdown and round_end, and in lobby while the auto-start
        hold runs; null while waiting."""
        if self._phase in ("lobby", "countdown", "round_end") and self._phase_ticks_left is not None:
            return self._ticks_to_ms(self._phase_ticks_left)
        return None

    # --- Internal: validation ----------------------------------------------
    @staticmethod
    def _validate_assignments(assignments: tuple[Assignment, ...]) -> tuple[Assignment, ...]:
        if len(assignments) > 4:
            raise SimulationError("INVALID_INPUT", "at most four assignments")
        seen_slots: set[tuple[int, str]] = set()
        seen_members: set[str] = set()
        for a in assignments:
            if not isinstance(a, Assignment):
                raise SimulationError("INVALID_INPUT", "expected Assignment records")
            if not a.member_id:
                raise SimulationError("INVALID_INPUT", "member_id is required")
            if (a.team, a.role) not in CANONICAL_SLOTS:
                raise SimulationError(
                    "INVALID_INPUT", f"invalid slot {(a.team, a.role)!r}"
                )
            if (a.team, a.role) in seen_slots:
                raise SimulationError("INVALID_INPUT", "duplicate team/role slot")
            if a.member_id in seen_members:
                raise SimulationError("INVALID_INPUT", "duplicate member_id")
            seen_slots.add((a.team, a.role))
            seen_members.add(a.member_id)
        return tuple(
            sorted(assignments, key=lambda a: CANONICAL_SLOTS.index((a.team, a.role)))
        )
