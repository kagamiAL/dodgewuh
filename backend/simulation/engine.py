"""The authoritative gameplay simulation.

Implements the `Simulation` seam specified in plans/03-api-contracts.md. Every
method is synchronous and socket-free. No FastAPI, Pydantic, WebSocket, AWS or
PlayCanvas import appears anywhere in this package.

All eight seam methods carry their final production signatures so Alan
integrates once and never rebases on a signature change. Live now: lobby/reset
state, full snapshot projection, apply_input validation with room-wide ordinal
defense, fixed-step movement with half-court clamps and stale-input stop,
countdown -> active, reset/abort to lobby, Hold acquisition and ownership, safe
cancel and the no-throw zone, and constant-speed flight with relative-motion
swept collision, wall/expiry respawn and earliest-hit resolution.

Not yet implemented, and listed in HANDOFF.md so no consumer assumes otherwise:
hit SCORING, the 3600-tick timeout draw, round_end/role_switch/match_end, role
swapping, rematch (task 7-8) and the readiness abort guard.

Task 6 resolves a hit into state.result and freezes the round there, because
02 says a hit ends the round immediately but the round_end transition and the
score itself belong to task 7. So a decided round currently shows phase=active
with a non-null result and no further gameplay, and the score stays 0. Task 7
replaces that freeze with the real round_end transition in the same tick, at
which point result-during-active stops being observable. Nothing here is
silently wrong: the outcome is decided and published, it is just not yet
counted.

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


@dataclass(slots=True)
class _LegsInput:
    move: Vec2
    received_ms: int | None


@dataclass(slots=True)
class _ArmsState:
    hold: bool
    aim: Vec2
    received_ms: int | None


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
        # Set the tick a hit or draw is resolved. 02: "A hit ends the round
        # immediately." Task 7 turns this into the round_end transition and the
        # score; until then it freezes gameplay so no input changes a decided
        # round, which is what "no commands affect results after phase leaves
        # active" protects.
        self._round_decided: bool = False

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
        placed = {a.member_id for a in supplied}
        for slot in CANONICAL_SLOTS:
            if slot in slots:
                continue
            existing = next(
                (
                    a.member_id
                    for a in self._assignments
                    if (a.team, a.role) == slot and a.member_id not in placed
                ),
                None,
            )
            if existing is not None:
                slots[slot] = existing
                placed.add(existing)

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
        for a in self._assignments:
            if a.member_id not in self._connected_ids:
                raise SimulationError("NOT_READY", f"{a.member_id} is not connected")
            if a.member_id not in self._ready_ids:
                raise SimulationError("NOT_READY", f"{a.member_id} is not ready")

        self._score = {1: 0, 2: 0}
        self._result = None
        self._winner = None
        self._round = 1
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

        phase = self._phase
        self._tick += 1

        if phase == "active":
            # The deciding tick itself did elapse, so it still counts; every
            # tick after it does not. 03: remaining_ms retains the ended
            # round's value rather than draining on past a finished round.
            was_decided = self._round_decided
            self._step_active(now_ms)
            if not was_decided:
                self._active_ticks += 1
        elif phase == "countdown":
            if self._phase_ticks_left is not None:
                self._phase_ticks_left -= 1
                if self._phase_ticks_left <= 0:
                    self._enter_active()
        else:
            # lobby holds. round_end / role_switch / match_end are added in M5;
            # the tick still advances, which is what 03 requires.
            self._pending.clear()

    def _step_active(self, now_ms: int) -> None:
        if self._round_decided:
            # The round is over; only task 7's transition is still owed. Discard
            # input rather than letting it mutate a decided outcome.
            self._pending.clear()
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
                if arms.hold:
                    arms.hold = False
                    self._drop_held(team)

        # The swept collision in (5) needs each character's movement segment
        # for this tick, so remember where they started before moving them.
        prev_pos = {team: self._characters[team].pos for team in K.TEAMS}
        for team in K.TEAMS:
            char = self._characters[team]
            move = self._legs_input[team].move
            if move.x or move.z:
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

        # (5) Advance flight, resolve the earliest valid hit, then respawns.
        self._step_flight(prev_pos)

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
        char.held_ball_id = None

    def _sync_held_balls(self) -> None:
        for team in K.TEAMS:
            held = self._characters[team].held_ball_id
            if held is not None:
                self._balls[held].pos = self._characters[team].pos

    # --- Internal: flight, collision and respawn ----------------------------
    def _step_flight(self, prev_pos: dict[int, Vec2]) -> None:
        """02 step 5: advance flight, resolve the earliest valid hit, respawns.

        Flight is constant-speed and flat: velocity never changes, there is no
        bounce, and y height never enters a collision decision. Each ball is
        clipped to its wall/lifetime endpoint for this tick BEFORE the hit test,
        and a hit at or before that endpoint counts.

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
        plans: list[tuple[str, Vec2, bool, float | None]] = []
        for ball_id in K.BALL_IDS:
            ball = self._balls[ball_id]
            if ball.mode != "flying":
                continue

            disp = G.scale(ball.velocity, K.DT)
            exit_at = G.wall_exit_fraction(ball.pos, disp)
            limit = 1.0 if exit_at is None else exit_at
            endpoint = G.add(ball.pos, G.scale(disp, limit))

            # _release is the only writer of mode='flying' and always records a
            # shooter team, so the opponent lookup below is always defined.
            victim = K.opponent(ball.shooter_team)  # type: ignore[arg-type]
            hit_at = G.swept_hit(
                ball.pos,
                disp,
                prev_pos[victim],
                self._characters[victim].pos,
                limit,
            )
            plans.append((ball_id, endpoint, exit_at is not None, hit_at))

        for ball_id, endpoint, _, _ in plans:
            ball = self._balls[ball_id]
            ball.pos = endpoint
            ball.flight_ticks += 1

        # --- Earliest valid hit. Ties use ball ID; opposing hits within 1e-9
        # of each other are a draw awarding no point.
        decided = self._resolve_hit(plans)
        if decided is not None:
            self._result = decided
            self._round_decided = True
            # The round ended inside this tick, so no respawn starts or runs:
            # the next round resets the arena anyway. The hit ball stays flying
            # where the advance left it, matching the round_end example in 03.
            return

        # --- Endpoint consequences: wall exit or lifetime expiry respawns.
        for ball_id, _, left_court, _ in plans:
            ball = self._balls[ball_id]
            if left_court or ball.flight_ticks >= K.FLIGHT_TICKS:
                self._begin_respawn(ball)

        # --- Then respawns, per the step order in 02.
        for ball_id in already_respawning:
            ball = self._balls[ball_id]
            ball.respawn_ticks -= 1
            if ball.respawn_ticks <= 0:
                ball.respawn_ticks = 0
                ball.mode = "ground"
                spawn_x, spawn_z = K.BALL_SPAWNS[ball_id]
                ball.pos = Vec2(spawn_x, spawn_z)

    def _resolve_hit(
        self, plans: list[tuple[str, Vec2, bool, float | None]]
    ) -> ResultDTO | None:
        """Pick the one outcome this tick, or None if nothing connected.

        02: compute the earliest time of impact in the tick, break equal times
        by ball ID, and award a draw with no points if two OPPOSING hits land
        within 1e-9 of each other. Later candidates are ignored outright.
        """
        candidates = [
            (hit_at, ball_id) for ball_id, _, _, hit_at in plans if hit_at is not None
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

    # --- Seam: snapshot -----------------------------------------------------
    def snapshot(self) -> StateDTO:
        """Full immutable state. Frozen dataclasses of tuples all the way down."""
        characters = tuple(
            CharacterDTO(
                team=team,  # type: ignore[arg-type]
                pos=self._characters[team].pos,
                aim=self._characters[team].aim,
                held_ball_id=self._characters[team].held_ball_id,
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
        )

    # --- Seam: events -------------------------------------------------------
    def drain_events(self) -> list[SimEvent]:
        """Ordered events since the last drain. Exactly-once."""
        events = self._events
        self._events = []
        return events

    # --- Internal: phases ---------------------------------------------------
    def _enter_countdown(self) -> None:
        self._active_ticks = 0
        self._result = None
        self._round_decided = False
        self._reset_arena()
        self._transition("countdown", K.COUNTDOWN_TICKS)

    def _enter_active(self) -> None:
        # Fresh movement is allowed on active entry, but Hold starts false.
        self._transition("active", None)

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
        self._round_decided = False
        self._winner = None
        self._ready_ids = frozenset()
        self._reset_arena()
        self._transition("lobby", None)

    def _transition(self, phase: Phase, phase_ticks: int | None) -> None:
        """Every phase transition clears latched controls and bumps epoch."""
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
        """Non-null only in countdown and round_end; null while waiting."""
        if self._phase in ("countdown", "round_end") and self._phase_ticks_left is not None:
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
