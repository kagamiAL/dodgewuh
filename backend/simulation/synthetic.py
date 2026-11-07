"""Synthetic diagnostic runner and fixture emitter. No framework imports.

Per the dodgewuh project instruction and 06, this is a MANUAL DIAGNOSTIC TOOL,
not a test suite: there is no test framework, no test dependency, no test file
and no test directory anywhere in this package, and no milestone or handoff is
gated on an automated test command. The runner drives the real Simulation
methods with the real command DTOs — no alternate control API and no temporary
interface to replace later — and prints what it observed against the rule in
02/03 that each observation comes from, for a human to read and judge.

It is also the runtime validator for the fixtures handed to Alan, which the
instruction explicitly retains.

    PYTHONPATH=backend python -m simulation.synthetic
    PYTHONPATH=backend python -m simulation.synthetic --fixtures backend/simulation/fixtures

Milestone 1 covers the deterministic movement surface: four directions,
diagonal speed cap, both half-court clamps, all four ball spawns, stale-input
stop, replay determinism, and the epoch/ordinal/role rejection paths.
Acquisition, flight, collision, scoring and the round lifecycle arrive in
M3-M6 and get their scenarios then.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import asdict, is_dataclass
from typing import Any

from . import constants as K
from .engine import Simulation
from .types import (ArmsCommand, Assignment, InputRejected, LegsCommand,
                    SimulationError, Vec2)

# Readable substitutes for opaque production IDs, as used in 03's examples.
P1, P2, P3, P4 = "p1", "p2", "p3", "p4"

FOUR = (
    Assignment(member_id=P1, team=1, role="arms"),
    Assignment(member_id=P2, team=1, role="legs"),
    Assignment(member_id=P3, team=2, role="arms"),
    Assignment(member_id=P4, team=2, role="legs"),
)

TOL = 1e-9


# --- Diagnostic reporting ---------------------------------------------------
# Per 06, the synthetic runner is a manual diagnostic tool, not a test suite:
# it drives the real Simulation and reports what it observed against the rule
# each observation came from, so a human can read the output and judge it.
class Diagnostics:
    """Collects observations and reports deviations from the specified rules."""

    def __init__(self) -> None:
        self.matched = 0
        self.deviations: list[str] = []

    def observe(self, rule: str, holds: bool, detail: str = "") -> None:
        if holds:
            self.matched += 1
            print(f"  ok         {rule}")
        else:
            self.deviations.append(rule)
            suffix = f" -- {detail}" if detail else ""
            print(f"  DEVIATION  {rule}{suffix}")

    def note(self, text: str) -> None:
        """Record an observed value that needs a human read, not a verdict."""
        print(f"  observed   {text}")


def near(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


# --- Helpers ----------------------------------------------------------------
def boot_to_active(now_ms: int = 0) -> Simulation:
    """Create a room, satisfy readiness, start, and run out the countdown."""
    sim = Simulation(FOUR)
    sim.set_readiness(
        ready_member_ids=frozenset({P1, P2, P3, P4}),
        connected_member_ids=frozenset({P1, P2, P3, P4}),
        screen_count=1,
        host_connected=True,
    )
    sim.control("start")
    for i in range(K.COUNTDOWN_TICKS):
        sim.step(now_ms + i)
    sim.drain_events()
    return sim


def legs_member(sim: Simulation, team: int) -> str:
    for a in sim.snapshot().assignments:
        if a.team == team and a.role == "legs":
            return a.member_id
    raise AssertionError("no legs assignment")


def character(sim: Simulation, team: int):
    for c in sim.snapshot().characters:
        if c.team == team:
            return c
    raise AssertionError("no character")


def arms_member(sim: Simulation, team: int) -> str:
    for a in sim.snapshot().assignments:
        if a.team == team and a.role == "arms":
            return a.member_id
    raise AssertionError("no arms assignment")


def ball(sim: Simulation, ball_id: str):
    for b in sim.snapshot().balls:
        if b.ball_id == ball_id:
            return b
    raise AssertionError(f"no ball {ball_id}")


class Hands:
    """Drives one team's Arms phone through the real apply_input seam."""

    def __init__(self, sim: Simulation, team: int, ordinal: int | None = None,
                 now_ms: int = 0):
        self.sim = sim
        self.team = team
        self.member = arms_member(sim, team)
        # The receive ordinal is room-wide, so continue the room's sequence
        # rather than restarting at 1 (which the engine rightly rejects).
        self.ordinal = ordinal if ordinal is not None else sim._last_ordinal + 1  # noqa: SLF001
        self.now_ms = now_ms
        self.forward = Vec2(0.0, 1.0 if team == 1 else -1.0)

    def send(self, action: str, aim: Vec2 | None = None, strength: float | None = None):
        self.sim.apply_input(
            self.member,
            ArmsCommand(
                seq=self.ordinal,
                epoch=self.sim.snapshot().epoch,
                aim=aim or self.forward,
                action=action,  # type: ignore[arg-type]
                strength=strength,
            ),
            received_ms=self.now_ms,
            ordinal=self.ordinal,
        )
        self.ordinal += 1
        return self

    def step(self):
        self.sim.step(self.now_ms)
        self.now_ms += 17
        return self


def place(sim: Simulation, team: int, x: float, z: float) -> None:
    """Teleport a character for a boundary check.

    Reaches into internals deliberately: these scenarios probe exact geometric
    boundaries, and walking there by command would accumulate float drift and
    obscure the very boundary under examination.
    """
    sim._characters[team].pos = Vec2(x, z)  # noqa: SLF001
    sim._sync_held_balls()  # noqa: SLF001


def put_ball(sim: Simulation, ball_id: str, x: float, z: float) -> None:
    sim._balls[ball_id].pos = Vec2(x, z)  # noqa: SLF001


def clear_ground_balls(sim: Simulation, keep: tuple[str, ...]) -> None:
    """Park unwanted balls far away so a scenario isolates specific ones."""
    for bid in sim._balls:  # noqa: SLF001
        if bid not in keep:
            sim._balls[bid].pos = Vec2(0.0, 0.0)  # noqa: SLF001
            sim._balls[bid].mode = "respawning"  # noqa: SLF001
            sim._balls[bid].respawn_ticks = 10_000  # noqa: SLF001


def drive(
    sim: Simulation,
    team: int,
    move: Vec2,
    ticks: int,
    ordinal: int,
    now_ms: int = 0,
) -> tuple[int, int]:
    """Send one move per tick and step. Returns (next_ordinal, next_now_ms)."""
    member = legs_member(sim, team)
    epoch = sim.snapshot().epoch
    for _ in range(ticks):
        sim.apply_input(
            member,
            LegsCommand(seq=ordinal, epoch=epoch, move=move),
            received_ms=now_ms,
            ordinal=ordinal,
        )
        ordinal += 1
        sim.step(now_ms)
        now_ms += 17
    return ordinal, now_ms


# --- Scenarios --------------------------------------------------------------
def scenario_reset_snapshot(d: Diagnostics) -> None:
    print("\n[reset/lobby snapshot]")
    sim = Simulation(FOUR)
    s = sim.snapshot()

    d.observe("lobby phase", s.phase == "lobby", s.phase)
    d.observe("tick 0", s.tick == 0)
    d.observe("epoch 0", s.epoch == 0)
    d.observe("round 0", s.round == 0)
    d.observe("score zero", s.score.t1 == 0 and s.score.t2 == 0)
    d.observe("remaining_ms 60000", s.remaining_ms == 60000, str(s.remaining_ms))
    d.observe("phase_remaining_ms null", s.phase_remaining_ms is None)
    d.observe("result null", s.result is None)
    d.observe("winner null", s.winner is None)

    d.observe("exactly two characters", len(s.characters) == 2, str(len(s.characters)))
    d.observe("characters sorted by team", [c.team for c in s.characters] == [1, 2])
    t1, t2 = s.characters
    d.observe("T1 spawn (0,-6)", (t1.pos.x, t1.pos.z) == K.T1_SPAWN, str(t1.pos))
    d.observe("T2 spawn (0,6)", (t2.pos.x, t2.pos.z) == K.T2_SPAWN, str(t2.pos))
    d.observe("T1 aim forward +z", (t1.aim.x, t1.aim.z) == (0.0, 1.0), str(t1.aim))
    d.observe("T2 aim forward -z", (t2.aim.x, t2.aim.z) == (0.0, -1.0), str(t2.aim))
    d.observe("no held balls", t1.held_ball_id is None and t2.held_ball_id is None)

    d.observe("exactly four balls", len(s.balls) == 4, str(len(s.balls)))
    d.observe(
        "balls sorted by id",
        [b.ball_id for b in s.balls] == ["b1", "b2", "b3", "b4"],
    )
    spawns_ok = all(
        (b.pos.x, b.pos.z) == K.BALL_SPAWNS[b.ball_id] for b in s.balls
    )
    d.observe("all four ball spawns exact", spawns_ok)
    d.observe("all balls grounded", all(b.mode == "ground" for b in s.balls))
    d.observe(
        "no ownership in lobby",
        all(b.owner_team is None and b.shooter_team is None for b in s.balls),
    )
    d.observe(
        "zero velocity and respawn",
        all(
            b.velocity.x == 0 and b.velocity.z == 0 and b.respawn_in_ms == 0
            for b in s.balls
        ),
    )
    d.observe("assignment_version 1 for four", s.assignment_version == 1)


def scenario_four_directions(d: Diagnostics) -> None:
    print("\n[movement: ten moves in four directions]")
    step = K.MOVE_SPEED * K.DT
    cases = (
        ("forward +z (T1)", 1, Vec2(0.0, 1.0), 0.0, +10 * step),
        ("backward -z (T1)", 1, Vec2(0.0, -1.0), 0.0, -10 * step),
        ("right +x (T1)", 1, Vec2(1.0, 0.0), +10 * step, 0.0),
        ("left -x (T1)", 1, Vec2(-1.0, 0.0), -10 * step, 0.0),
    )
    for name, team, move, dx, dz in cases:
        sim = boot_to_active()
        before = character(sim, team).pos
        drive(sim, team, move, 10, ordinal=1)
        after = character(sim, team).pos
        ok = near(after.x - before.x, dx, 1e-9) and near(after.z - before.z, dz, 1e-9)
        d.observe(
            f"ten moves {name}",
            ok,
            f"moved ({after.x - before.x:.6f},{after.z - before.z:.6f}) "
            f"expected ({dx:.6f},{dz:.6f})",
        )


def scenario_diagonal_speed(d: Diagnostics) -> None:
    print("\n[movement: diagonal magnitude capped at 1]")
    sim = boot_to_active()
    before = character(sim, 1).pos
    # A unit diagonal: already magnitude 1, so speed must stay 3.5 m/s.
    inv = 1.0 / math.sqrt(2.0)
    drive(sim, 1, Vec2(inv, inv), 10, ordinal=1)
    after = character(sim, 1).pos
    travelled = math.hypot(after.x - before.x, after.z - before.z)
    expected = 10 * K.MOVE_SPEED * K.DT
    d.observe(
        "unit diagonal travels 3.5 m/s",
        near(travelled, expected, 1e-9),
        f"{travelled:.6f} vs {expected:.6f}",
    )

    # An over-long (1,1) is normalized, not rejected and not 4.95 m/s.
    sim2 = boot_to_active()
    member = legs_member(sim2, 1)
    epoch = sim2.snapshot().epoch
    try:
        sim2.apply_input(
            member,
            LegsCommand(seq=1, epoch=epoch, move=Vec2(1.0, 1.0)),
            received_ms=0,
            ordinal=1,
        )
        raised = False
    except SimulationError as exc:
        raised = exc.code == "INVALID_INPUT"
    d.observe(
        "(1,1) magnitude 1.414 rejected as INVALID_INPUT",
        raised,
        "03 allows magnitude <= 1.001 only",
    )

    # A diagonal with in-range components but magnitude just over 1 is the
    # only way to reach the 1.001 tolerance: normalized, not rejected.
    sim3 = boot_to_active()
    edge = 0.7072  # magnitude 1.000136...
    d.observe(
        "edge case really is slight excess",
        1.0 < math.hypot(edge, edge) <= K.MOVE_MAGNITUDE_TOLERANCE,
        f"magnitude {math.hypot(edge, edge):.6f}",
    )
    before3 = character(sim3, 1).pos
    drive(sim3, 1, Vec2(edge, edge), 10, ordinal=1)
    after3 = character(sim3, 1).pos
    travelled3 = math.hypot(after3.x - before3.x, after3.z - before3.z)
    d.observe(
        "slight magnitude excess normalized to 3.5 m/s",
        near(travelled3, expected, 1e-9),
        f"{travelled3:.6f} vs {expected:.6f}",
    )

    # A component outside [-1, 1] is refused outright, per 03 input.legs.
    sim4 = boot_to_active()
    try:
        sim4.apply_input(
            legs_member(sim4, 1),
            LegsCommand(seq=1, epoch=sim4.snapshot().epoch, move=Vec2(0.0, 1.0005)),
            received_ms=0,
            ordinal=1,
        )
        component_raised = False
    except SimulationError as exc:
        component_raised = exc.code == "INVALID_INPUT"
    d.observe("out-of-range component rejected", component_raised)


def scenario_clamps(d: Diagnostics) -> None:
    print("\n[movement: half-court clamps]")
    # Far right wall.
    sim = boot_to_active()
    drive(sim, 1, Vec2(1.0, 0.0), 400, ordinal=1)
    d.observe(
        "T1 clamps at x = +5.55",
        near(character(sim, 1).pos.x, K.CHAR_X_LIMIT, 1e-12),
        str(character(sim, 1).pos.x),
    )

    # Own back wall.
    sim = boot_to_active()
    drive(sim, 1, Vec2(0.0, -1.0), 400, ordinal=1)
    d.observe(
        "T1 clamps at z = -8.55",
        near(character(sim, 1).pos.z, K.T1_Z_MIN, 1e-12),
        str(character(sim, 1).pos.z),
    )

    # Centre line: T1 may not cross into positive z.
    sim = boot_to_active()
    drive(sim, 1, Vec2(0.0, 1.0), 400, ordinal=1)
    d.observe(
        "T1 cannot cross centre, stops at z = -0.45",
        near(character(sim, 1).pos.z, K.T1_Z_MAX, 1e-12),
        str(character(sim, 1).pos.z),
    )

    # Team 2's mirror limits.
    sim = boot_to_active()
    drive(sim, 2, Vec2(0.0, -1.0), 400, ordinal=1)
    d.observe(
        "T2 cannot cross centre, stops at z = +0.45",
        near(character(sim, 2).pos.z, K.T2_Z_MIN, 1e-12),
        str(character(sim, 2).pos.z),
    )
    sim = boot_to_active()
    drive(sim, 2, Vec2(-1.0, 0.0), 400, ordinal=1)
    d.observe(
        "T2 clamps at x = -5.55",
        near(character(sim, 2).pos.x, -K.CHAR_X_LIMIT, 1e-12),
        str(character(sim, 2).pos.x),
    )


def scenario_stale_stop(d: Diagnostics) -> None:
    print("\n[movement: stale input stop at 250 ms]")
    sim = boot_to_active()
    member = legs_member(sim, 1)
    epoch = sim.snapshot().epoch

    # One valid move received at t=1000, then silence.
    sim.apply_input(
        member,
        LegsCommand(seq=1, epoch=epoch, move=Vec2(0.0, 1.0)),
        received_ms=1000,
        ordinal=1,
    )
    sim.step(1000)
    moved_once = character(sim, 1).pos.z

    # Still fresh at exactly 250 ms of age: keeps moving.
    sim.step(1250)
    fresh = character(sim, 1).pos.z
    d.observe(
        "input is still fresh at exactly 250 ms",
        fresh > moved_once,
        f"{fresh} vs {moved_once}",
    )

    # One millisecond past the timeout: movement stops.
    sim.step(1251)
    stopped = character(sim, 1).pos.z
    sim.step(1400)
    still = character(sim, 1).pos.z
    d.observe("stale input stops movement past 250 ms", near(stopped, still, 1e-12))


def scenario_rejections(d: Diagnostics) -> None:
    print("\n[input defense: epoch, ordinal, role, phase]")
    sim = boot_to_active()
    member = legs_member(sim, 1)
    arms_member = next(
        a.member_id for a in sim.snapshot().assignments if a.team == 1 and a.role == "arms"
    )
    epoch = sim.snapshot().epoch

    def expect(name: str, code: str, fn) -> None:
        try:
            fn()
        except SimulationError as exc:
            d.observe(name, exc.code == code, f"got {exc.code}, wanted {code}")
        else:
            d.observe(name, False, f"no raise, wanted {code}")

    expect(
        "old epoch rejected as STALE_EPOCH",
        "STALE_EPOCH",
        lambda: sim.apply_input(
            member,
            LegsCommand(seq=1, epoch=epoch - 1, move=Vec2(0.0, 1.0)),
            received_ms=0,
            ordinal=10,
        ),
    )
    sim.apply_input(
        member,
        LegsCommand(seq=1, epoch=epoch, move=Vec2(0.0, 1.0)),
        received_ms=0,
        ordinal=20,
    )
    expect(
        "replayed ordinal rejected as OLD_SEQ",
        "OLD_SEQ",
        lambda: sim.apply_input(
            member,
            LegsCommand(seq=2, epoch=epoch, move=Vec2(0.0, 1.0)),
            received_ms=0,
            ordinal=20,
        ),
    )
    expect(
        "legs command from arms member rejected as WRONG_ROLE",
        "WRONG_ROLE",
        lambda: sim.apply_input(
            arms_member,
            LegsCommand(seq=1, epoch=epoch, move=Vec2(0.0, 1.0)),
            received_ms=0,
            ordinal=30,
        ),
    )
    expect(
        "unknown member rejected as WRONG_ROLE",
        "WRONG_ROLE",
        lambda: sim.apply_input(
            "nobody",
            LegsCommand(seq=1, epoch=epoch, move=Vec2(0.0, 1.0)),
            received_ms=0,
            ordinal=40,
        ),
    )
    expect(
        "backward aim rejected as INVALID_INPUT",
        "INVALID_INPUT",
        lambda: sim.apply_input(
            arms_member,
            ArmsCommand(
                seq=1, epoch=epoch, aim=Vec2(0.0, -1.0), action="aim", strength=None
            ),
            received_ms=0,
            ordinal=50,
        ),
    )
    expect(
        "strength on non-release rejected as INVALID_INPUT",
        "INVALID_INPUT",
        lambda: sim.apply_input(
            arms_member,
            ArmsCommand(
                seq=2, epoch=epoch, aim=Vec2(0.0, 1.0), action="press", strength=0.5
            ),
            received_ms=0,
            ordinal=60,
        ),
    )

    # A reconnected phone restarts seq at 1; the room ordinal keeps rising, so
    # the command must still be accepted.
    sim.apply_input(
        member,
        LegsCommand(seq=1, epoch=epoch, move=Vec2(0.0, 1.0)),
        received_ms=0,
        ordinal=70,
    )
    d.observe("reconnect seq=1 accepted on a newer ordinal", True)

    # Input outside active is refused.
    lobby = Simulation(FOUR)
    expect(
        "input in lobby rejected as INVALID_PHASE",
        "INVALID_PHASE",
        lambda: lobby.apply_input(
            legs_member(lobby, 1),
            LegsCommand(seq=1, epoch=0, move=Vec2(0.0, 1.0)),
            received_ms=0,
            ordinal=1,
        ),
    )


def scenario_determinism(d: Diagnostics) -> None:
    print("\n[determinism: recorded command list replays identically]")
    script = [
        (1, Vec2(0.0, 1.0), 12),
        (2, Vec2(-1.0, 0.0), 7),
        (1, Vec2(0.70710678, 0.70710678), 23),
        (2, Vec2(0.0, -1.0), 31),
        (1, Vec2(-1.0, 0.0), 5),
    ]

    def run() -> Any:
        sim = boot_to_active()
        ordinal, now = 1, 0
        for team, move, ticks in script:
            ordinal, now = drive(sim, team, move, ticks, ordinal, now)
        return sim.snapshot()

    a, b = run(), run()
    d.observe("two runs produce an identical final snapshot", a == b)

    c = run()
    d.observe("a third run still matches", a == c)


def scenario_lifecycle_m1(d: Diagnostics) -> None:
    print("\n[lifecycle available in M1: start gate, countdown, reset]")
    sim = Simulation(FOUR)

    try:
        sim.control("start")
        d.observe("start without readiness is refused", False, "no raise")
    except SimulationError as exc:
        d.observe(
            "start without readiness refused as NOT_READY",
            exc.code == "NOT_READY",
            exc.code,
        )

    sim.set_readiness(
        ready_member_ids=frozenset({P1, P2, P3}),
        connected_member_ids=frozenset({P1, P2, P3, P4}),
        screen_count=1,
        host_connected=True,
    )
    try:
        sim.control("start")
        d.observe("start with three ready phones is refused", False, "no raise")
    except SimulationError as exc:
        d.observe(
            "start with an unready phone refused as NOT_READY",
            exc.code == "NOT_READY",
            exc.code,
        )

    sim.set_readiness(
        ready_member_ids=frozenset({P1, P2, P3, P4}),
        connected_member_ids=frozenset({P1, P2, P3, P4}),
        screen_count=0,
        host_connected=True,
    )
    try:
        sim.control("start")
        d.observe("start without a screen is refused", False, "no raise")
    except SimulationError as exc:
        d.observe(
            "start without a screen refused as NOT_READY",
            exc.code == "NOT_READY",
            exc.code,
        )

    sim.set_readiness(
        ready_member_ids=frozenset({P1, P2, P3, P4}),
        connected_member_ids=frozenset({P1, P2, P3, P4}),
        screen_count=1,
        host_connected=True,
    )
    sim.control("start")
    s = sim.snapshot()
    d.observe("start enters countdown", s.phase == "countdown", s.phase)
    d.observe("countdown shows 3000 ms", s.phase_remaining_ms == 3000, str(s.phase_remaining_ms))
    d.observe("round becomes 1", s.round == 1)
    d.observe("epoch incremented on transition", s.epoch == 1, str(s.epoch))
    events = sim.drain_events()
    d.observe("start emitted PhaseChanged", len(events) == 1, str(events))
    d.observe("drain is exactly once", sim.drain_events() == [])

    entry_tick = s.tick
    for i in range(K.COUNTDOWN_TICKS - 1):
        sim.step(i)
    d.observe("still counting down one tick early", sim.snapshot().phase == "countdown")
    sim.step(K.COUNTDOWN_TICKS)
    s2 = sim.snapshot()
    d.observe("countdown ends after exactly 180 ticks", s2.phase == "active", s2.phase)
    d.observe(
        "tick advanced 180 during countdown",
        s2.tick == entry_tick + K.COUNTDOWN_TICKS,
        f"{s2.tick} vs {entry_tick + K.COUNTDOWN_TICKS}",
    )
    d.observe("active has null phase_remaining_ms", s2.phase_remaining_ms is None)
    d.observe("active round clock starts at 60000", s2.remaining_ms == 60000)

    # Reset from a live phase returns to lobby, bumps epoch, keeps assignments.
    before_epoch = s2.epoch
    sim.control("reset")
    s3 = sim.snapshot()
    d.observe("reset returns to lobby", s3.phase == "lobby", s3.phase)
    d.observe("reset increments epoch", s3.epoch > before_epoch)
    d.observe("reset retains assignments", s3.assignments == FOUR)
    d.observe("reset clears round", s3.round == 0)
    d.observe("reset restores spawns", (s3.characters[0].pos.x, s3.characters[0].pos.z) == K.T1_SPAWN)

    # A reset while already in lobby still bumps epoch and emits PhaseChanged.
    sim.drain_events()
    lobby_epoch = sim.snapshot().epoch
    sim.control("reset")
    d.observe("lobby reset still increments epoch", sim.snapshot().epoch > lobby_epoch)
    d.observe("lobby reset still emits PhaseChanged", len(sim.drain_events()) == 1)

    # tick never resets, in any phase.
    t_before = sim.snapshot().tick
    sim.step(0)
    d.observe("tick advances in lobby too", sim.snapshot().tick == t_before + 1)


def scenario_immutability(d: Diagnostics) -> None:
    print("\n[immutability: networking cannot mutate simulation]")
    sim = boot_to_active()
    s = sim.snapshot()
    try:
        s.characters[0].pos.x = 99.0  # type: ignore[misc]
        d.observe("snapshot vectors are frozen", False, "mutation succeeded")
    except Exception:
        d.observe("snapshot vectors are frozen", True)
    d.observe("characters is a tuple", isinstance(s.characters, tuple))
    d.observe("balls is a tuple", isinstance(s.balls, tuple))
    d.observe("assignments is a tuple", isinstance(s.assignments, tuple))

    drive(sim, 1, Vec2(0.0, 1.0), 5, ordinal=1)
    d.observe(
        "an older snapshot is unaffected by later steps",
        s.characters[0].pos.z == K.T1_SPAWN[1],
    )


# --- Task 5: acquisition, ownership, cancel, no-throw zone ------------------
def scenario_pickup(d: Diagnostics) -> None:
    print("\n[acquisition: nearest in range, ties by ball ID]")

    # Nearest grounded ball wins.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1", "b2"))
    place(sim, 1, 0.0, -3.0)
    put_ball(sim, "b1", 1.0, -3.0)  # 1.0 m away
    put_ball(sim, "b2", 0.5, -3.0)  # 0.5 m away - nearer
    Hands(sim, 1).send("press").step()
    d.observe("nearest ball is acquired", character(sim, 1).held_ball_id == "b2",
              str(character(sim, 1).held_ball_id))

    # Equal distance -> lowest ball ID.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b3", "b4"))
    place(sim, 1, 0.0, -3.0)
    put_ball(sim, "b3", 0.8, -3.0)
    put_ball(sim, "b4", -0.8, -3.0)  # exactly the same distance
    Hands(sim, 1).send("press").step()
    d.observe("equal-distance tie breaks to the lower ball ID",
              character(sim, 1).held_ball_id == "b3",
              str(character(sim, 1).held_ball_id))

    # Inclusive range boundary at exactly 1.2 m.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -3.0)
    put_ball(sim, "b1", 0.0, -3.0 + K.PICKUP_RANGE)
    Hands(sim, 1).send("press").step()
    d.observe("pickup at exactly 1.2 m succeeds (inclusive)",
              character(sim, 1).held_ball_id == "b1")

    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -3.0)
    put_ball(sim, "b1", 0.0, -3.0 + K.PICKUP_RANGE + 1e-6)
    Hands(sim, 1).send("press").step()
    d.observe("pickup just beyond 1.2 m fails",
              character(sim, 1).held_ball_id is None)

    # Hold is retried each tick: walk into range while already holding Hold.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -5.0)
    put_ball(sim, "b1", 0.0, -3.0)
    h = Hands(sim, 1).send("press").step()
    d.observe("press out of range acquires nothing",
              character(sim, 1).held_ball_id is None)
    place(sim, 1, 0.0, -3.9)
    h.step()
    d.observe("latched Hold re-acquires once in range",
              character(sim, 1).held_ball_id == "b1")


def scenario_ownership(d: Diagnostics) -> None:
    print("\n[ownership: one ball each, never acquired twice]")
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1", "b2"))
    place(sim, 1, 0.0, -3.0)
    put_ball(sim, "b1", 0.3, -3.0)
    put_ball(sim, "b2", 0.4, -3.0)
    h = Hands(sim, 1).send("press").step()
    first = character(sim, 1).held_ball_id
    h.send("press").step()
    d.observe("a second press does not take a second ball",
              character(sim, 1).held_ball_id == first, str(first))
    held_count = sum(1 for b in sim.snapshot().balls if b.mode == "held")
    d.observe("exactly one ball is held", held_count == 1, str(held_count))

    b = ball(sim, first)
    d.observe("held ball reports owner_team", b.owner_team == 1, str(b.owner_team))
    d.observe("held ball has no shooter_team", b.shooter_team is None)
    d.observe("held ball has zero velocity", (b.velocity.x, b.velocity.z) == (0.0, 0.0))

    # The opponent cannot take a ball that is already held.
    place(sim, 2, 0.0, 0.5)
    put_ball(sim, first, 0.0, 0.5)  # park it right on top of Team 2
    Hands(sim, 2).send("press").step()
    d.observe("a held ball cannot be acquired by the opponent",
              character(sim, 2).held_ball_id is None,
              str(character(sim, 2).held_ball_id))

    # Held balls follow their character.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -3.0)
    put_ball(sim, "b1", 0.3, -3.0)
    Hands(sim, 1).send("press").step()
    drive(sim, 1, Vec2(0.0, 1.0), 10, ordinal=500)
    c, b = character(sim, 1), ball(sim, "b1")
    d.observe("held ball follows the character",
              (b.pos.x, b.pos.z) == (c.pos.x, c.pos.z), f"ball {b.pos} vs char {c.pos}")


def scenario_no_throw_zone(d: Diagnostics) -> None:
    print("\n[no-throw zone: inclusive boundary at abs(z) = 2.0]")

    def release_at(z: float, strength: float = 0.5):
        sim = boot_to_active()
        clear_ground_balls(sim, ("b1",))
        place(sim, 1, 0.0, z)
        put_ball(sim, "b1", 0.0, z)
        h = Hands(sim, 1).send("press")
        h.step()
        sim.drain_events()
        place(sim, 1, 0.0, z)
        h.send("release", strength=strength).step()
        return sim, sim.drain_events()

    # Exactly on the boundary: rejected, because the rule is inclusive.
    sim, events = release_at(-K.NO_THROW_ABS_Z)
    b = ball(sim, "b1")
    codes = [e.code for e in events if isinstance(e, InputRejected)]
    d.observe("release at exactly z = -2.0 does not launch", b.mode == "ground", b.mode)
    d.observe("release at the boundary emits NO_THROW_ZONE",
              codes == ["NO_THROW_ZONE"], str(codes))
    d.observe("safe cancel drops the ball at the character centre",
              (b.pos.x, b.pos.z) == (0.0, -K.NO_THROW_ABS_Z), str(b.pos))
    d.observe("safe cancel clears possession", character(sim, 1).held_ball_id is None)
    rejected = [e for e in events if isinstance(e, InputRejected)]
    d.observe("rejection carries ref_seq", rejected and rejected[0].ref_seq is not None,
              str(rejected[0].ref_seq) if rejected else "none")

    # Inside the zone, well clear of the boundary.
    sim, events = release_at(-1.0)
    d.observe("release deep inside the zone does not launch",
              ball(sim, "b1").mode == "ground")

    # Just outside: a legal throw.
    sim, events = release_at(-K.NO_THROW_ABS_Z - 1e-6)
    b = ball(sim, "b1")
    d.observe("release just outside the zone launches", b.mode == "flying", b.mode)
    d.observe("legal throw emits no rejection",
              not [e for e in events if isinstance(e, InputRejected)])
    d.observe("flying ball records shooter_team", b.shooter_team == 1, str(b.shooter_team))
    d.observe("flying ball has no owner_team", b.owner_team is None)


def scenario_throw_launch(d: Diagnostics) -> None:
    print("\n[release: launch offset and speed]")
    for strength, expected in ((0.0, 8.0), (0.5, 11.0), (1.0, 14.0)):
        sim = boot_to_active()
        clear_ground_balls(sim, ("b1",))
        place(sim, 1, 0.0, -4.0)
        put_ball(sim, "b1", 0.0, -4.0)
        h = Hands(sim, 1).send("press").step()
        place(sim, 1, 0.0, -4.0)
        h.send("release", strength=strength).step()
        b = ball(sim, "b1")
        speed = math.hypot(b.velocity.x, b.velocity.z)
        d.observe(f"strength {strength} gives speed {expected}",
                  near(speed, expected, 1e-9), f"{speed:.6f}")

    # Launch point is centre + aim * 0.65.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -4.0)
    put_ball(sim, "b1", 0.0, -4.0)
    h = Hands(sim, 1).send("press").step()
    place(sim, 1, 0.0, -4.0)
    h.send("release", strength=0.5).step()
    b = ball(sim, "b1")
    d.observe("launch at centre + aim x 0.65",
              near(b.pos.z, -4.0 + K.THROW_OFFSET, 1e-9) and near(b.pos.x, 0.0, 1e-12),
              str(b.pos))


def scenario_cancel_and_edges(d: Diagnostics) -> None:
    print("\n[cancel and same-tick edge ordering]")

    # Cancel drops without launching, anywhere on the court.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -6.0)
    put_ball(sim, "b1", 0.0, -6.0)
    h = Hands(sim, 1).send("press").step()
    place(sim, 1, 0.0, -6.0)
    h.send("cancel").step()
    b = ball(sim, "b1")
    d.observe("cancel never launches", b.mode == "ground", b.mode)
    d.observe("cancel drops at the character centre", (b.pos.x, b.pos.z) == (0.0, -6.0))
    d.observe("cancel has zero velocity", (b.velocity.x, b.velocity.z) == (0.0, 0.0))
    d.observe("cancel clears possession", character(sim, 1).held_ball_id is None)

    # Must press again after cancelling: the latch is gone.
    h.step()
    d.observe("no re-acquire after cancel without a fresh press",
              character(sim, 1).held_ball_id is None)

    # press + release in the SAME tick throws.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -6.0)
    put_ball(sim, "b1", 0.0, -6.0)
    Hands(sim, 1).send("press").send("release", strength=0.5).step()
    d.observe("press + release in one tick throws",
              ball(sim, "b1").mode == "flying", ball(sim, "b1").mode)

    # release then cancel in one tick: cancel cannot undo a legal throw.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -6.0)
    put_ball(sim, "b1", 0.0, -6.0)
    Hands(sim, 1).send("press").send("release", strength=0.5).send("cancel").step()
    d.observe("cancel after release cannot undo the throw",
              ball(sim, "b1").mode == "flying", ball(sim, "b1").mode)

    # A later aim cannot redirect an earlier release.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -6.0)
    put_ball(sim, "b1", 0.0, -6.0)
    straight = Vec2(0.0, 1.0)
    sideways = Vec2(0.6, 0.8)
    (Hands(sim, 1).send("press", aim=straight)
                  .send("release", aim=straight, strength=0.5)
                  .send("aim", aim=sideways).step())
    b = ball(sim, "b1")
    d.observe("a later aim does not redirect an earlier release",
              near(b.velocity.x, 0.0, 1e-12), f"vx={b.velocity.x}")

    # Releasing with no ball clears Hold and does nothing else.
    sim = boot_to_active()
    clear_ground_balls(sim, ())
    place(sim, 1, 0.0, -6.0)
    h = Hands(sim, 1).send("release", strength=0.5).step()
    flying = [b for b in sim.snapshot().balls if b.mode == "flying"]
    d.observe("release with no ball launches nothing", not flying)
    d.observe("release with no ball emits no rejection",
              not [e for e in sim.drain_events() if isinstance(e, InputRejected)])


def scenario_drop_paths(d: Diagnostics) -> None:
    print("\n[drop paths: stale input and phase transition]")

    # Stale Arms input drops the held ball.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -6.0)
    put_ball(sim, "b1", 0.0, -6.0)
    h = Hands(sim, 1)
    h.now_ms = 1000
    h.send("press")
    sim.step(1000)
    d.observe("ball acquired before silence", character(sim, 1).held_ball_id == "b1")
    sim.step(1251)  # 251 ms since the last Arms input
    d.observe("stale Arms input drops the held ball",
              character(sim, 1).held_ball_id is None)
    d.observe("dropped ball is grounded, not flying",
              ball(sim, "b1").mode == "ground", ball(sim, "b1").mode)

    # A phase transition drops the held ball too.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -6.0)
    put_ball(sim, "b1", 0.0, -6.0)
    Hands(sim, 1).send("press").step()
    d.observe("ball held before reset", character(sim, 1).held_ball_id == "b1")
    sim.control("reset")
    held = [b for b in sim.snapshot().balls if b.mode == "held"]
    d.observe("reset to lobby leaves no held ball", not held)
    d.observe("reset clears possession on the character",
              character(sim, 1).held_ball_id is None)


# --- Fixture emission -------------------------------------------------------
def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def envelope(state: Any, server_ms: int) -> dict[str, Any]:
    """Wrap a snapshot in the state.snapshot envelope shape from 03."""
    return {
        "v": 1,
        "type": "state.snapshot",
        "server_ms": server_ms,
        "payload": {"state": _plain(state)},
    }


def write_fixtures(directory: str) -> list[str]:
    os.makedirs(directory, exist_ok=True)
    written: list[str] = []

    lobby = Simulation(FOUR)
    fixtures = [("reset-lobby.json", envelope(lobby.snapshot(), 0))]

    sim = boot_to_active()
    ordinal, now = drive(sim, 1, Vec2(0.0, 1.0), 60, ordinal=1)
    drive(sim, 2, Vec2(-1.0, 0.0), 30, ordinal, now)
    fixtures.append(("active-movement.json", envelope(sim.snapshot(), 5000)))

    for name, payload in fixtures:
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
            handle.write("\n")
        written.append(path)
    return written


# --- Entry point ------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="simulation.synthetic",
        description="Drive the authoritative simulation through synthetic scenarios.",
    )
    parser.add_argument(
        "--fixtures",
        metavar="DIR",
        help="write snapshot fixtures as JSON into DIR and exit",
    )
    args = parser.parse_args(argv)

    if args.fixtures:
        for path in write_fixtures(args.fixtures):
            print(f"wrote {path}")
        return 0

    print("Authoritative gameplay simulation - synthetic runner")
    print("Milestone 1: DTOs, reset state, deterministic movement, input defense")

    diagnostics = Diagnostics()
    scenario_reset_snapshot(diagnostics)
    scenario_four_directions(diagnostics)
    scenario_diagonal_speed(diagnostics)
    scenario_clamps(diagnostics)
    scenario_stale_stop(diagnostics)
    scenario_rejections(diagnostics)
    scenario_determinism(diagnostics)
    scenario_lifecycle_m1(diagnostics)
    scenario_immutability(diagnostics)
    scenario_pickup(diagnostics)
    scenario_ownership(diagnostics)
    scenario_no_throw_zone(diagnostics)
    scenario_throw_launch(diagnostics)
    scenario_cancel_and_edges(diagnostics)
    scenario_drop_paths(diagnostics)

    total = diagnostics.matched + len(diagnostics.deviations)
    print(f"\n{diagnostics.matched}/{total} observations match the specified rules")
    if diagnostics.deviations:
        print("deviations from spec:")
        for rule in diagnostics.deviations:
            print(f"  - {rule}")
        return 1
    print("\nNot yet implemented (task 6 onward): ball flight advancement,")
    print("wall/expiry respawn, swept-circle collision, hit scoring, round")
    print("timeout, round_end/role_switch/match_end, role swapping, rematch,")
    print("and the readiness abort guard. A thrown ball is set flying with the")
    print("correct velocity and shooter team, but does not travel yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
