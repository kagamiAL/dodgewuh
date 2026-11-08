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

Covered so far: the deterministic movement surface (four directions, diagonal
speed cap, both half-court clamps, all four ball spawns, stale-input stop,
replay determinism, epoch/ordinal/role rejection); Hold acquisition, ownership,
safe cancel and the no-throw zone; constant-speed flight, wall/expiry respawn,
swept-circle collision and earliest-hit resolution; the full lifecycle --
exactly-once scoring, the 3600-tick timeout draw, round_end/role_switch/
match_end, every-round role swapping, readiness gating, first-to-three and a
complete four-round match with rematch; and the device guard -- abort to lobby
on phone/host/screen loss or revoked readiness, reset from every phase, and
rematch restricted to match_end.

Every ordered task in plans/agents/richard.md through task 8 is covered here.
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
                    PhaseChanged, RolesChanged, SimulationError, Vec2)

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


def launch_ball(
    sim: Simulation,
    ball_id: str,
    x: float,
    z: float,
    vx: float,
    vz: float,
    shooter_team: int,
    flight_ticks: int = 0,
) -> None:
    """Put a ball straight into flight, for collision geometry probes.

    Reaches into internals in the same spirit as place(): these scenarios pin
    exact impact geometry, and a few of them need a speed no legal throw can
    produce, which is the only way to show the solver is genuinely swept rather
    than a per-tick overlap sample. Legal-speed throws are exercised through the
    real release path in the task 5 scenarios and in scenario_collision.
    """
    b = sim._balls[ball_id]  # noqa: SLF001
    b.mode = "flying"
    b.pos = Vec2(x, z)
    b.velocity = Vec2(vx, vz)
    b.owner_team = None
    b.shooter_team = shooter_team
    b.flight_ticks = flight_ticks
    b.respawn_ticks = 0


def park_respawning(sim: Simulation, ball_id: str, x: float, z: float,
                    ticks: int = 30) -> None:
    """Hold a ball in respawning mode at a chosen spot."""
    b = sim._balls[ball_id]  # noqa: SLF001
    b.mode = "respawning"
    b.pos = Vec2(x, z)
    b.velocity = Vec2(0.0, 0.0)
    b.owner_team = None
    b.shooter_team = None
    b.respawn_ticks = ticks
    b.flight_ticks = 0


def step_until_result(sim: Simulation, limit: int = 120) -> int:
    """Step until the round is decided or `limit` ticks pass. Returns ticks."""
    ticks = 0
    while sim.snapshot().result is None and ticks < limit:
        sim.step(0)
        ticks += 1
    return ticks


def ready_all(sim: Simulation, screens: int = 1) -> None:
    """Supply the adapter facts for four connected, ready phones."""
    sim.set_readiness(
        ready_member_ids=frozenset({P1, P2, P3, P4}),
        connected_member_ids=frozenset({P1, P2, P3, P4}),
        screen_count=screens,
        host_connected=True,
    )


def assignment_map(sim: Simulation) -> dict[tuple[int, str], str]:
    """Current (team, role) -> member_id mapping."""
    return {(a.team, a.role): a.member_id for a in sim.snapshot().assignments}


def win_round(sim: Simulation, team: int = 1) -> None:
    """Land a hit for `team`. Leaves the simulation in round_end."""
    opponent = 2 if team == 1 else 1
    sign = 1.0 if team == 1 else -1.0
    place(sim, team, 0.0, -3.0 * sign)
    place(sim, opponent, 0.0, 3.0 * sign)
    launch_ball(sim, "b1", 0.0, -2.0 * sign, 0.0, 14.0 * sign, shooter_team=team)
    step_until_result(sim)


def draw_round(sim: Simulation) -> None:
    """Land two opposing hits at the same instant. Leaves round_end."""
    place(sim, 1, 0.0, -3.0)
    place(sim, 2, 0.0, 3.0)
    launch_ball(sim, "b1", 0.0, -1.0, 0.0, 10.0, shooter_team=1)
    launch_ball(sim, "b2", 0.0, 1.0, 0.0, -10.0, shooter_team=2)
    step_until_result(sim)


def run_out_phase(sim: Simulation, phase: str, limit: int = 400) -> int:
    """Step while the simulation is still in `phase`. Returns ticks spent."""
    ticks = 0
    while sim.snapshot().phase == phase and ticks < limit:
        sim.step(0)
        ticks += 1
    return ticks


def advance_to_next_active(sim: Simulation) -> None:
    """From round_end, reach the next round's active phase.

    Runs out the result display, supplies readiness at role_switch, then runs
    out the countdown — the same path four real phones take.
    """
    run_out_phase(sim, "round_end")
    if sim.snapshot().phase == "role_switch":
        ready_all(sim)
        run_out_phase(sim, "role_switch")
    run_out_phase(sim, "countdown")


def event_epochs(events: list[Any]) -> list[tuple[str, int]]:
    """Label and epoch of each transition event, in emission order."""
    out: list[tuple[str, int]] = []
    for e in events:
        if isinstance(e, PhaseChanged):
            out.append((f"phase:{e.state.phase}", e.state.epoch))
        elif isinstance(e, RolesChanged):
            out.append(("roles", e.epoch))
    return out


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

    # Launch point is centre + aim * 0.65. The release is step (4) of a tick and
    # flight advances in step (5) of the SAME tick, so one tick of travel at the
    # launch speed is already on the board when the step returns. That ordering
    # is the rule in 02, so the offset is checked through it rather than by
    # pretending the ball has not moved.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -4.0)
    put_ball(sim, "b1", 0.0, -4.0)
    h = Hands(sim, 1).send("press").step()
    place(sim, 1, 0.0, -4.0)
    h.send("release", strength=0.5).step()
    b = ball(sim, "b1")
    launched_z = -4.0 + K.THROW_OFFSET
    expected_z = launched_z + 11.0 * K.DT
    d.observe("launch at centre + aim x 0.65, then one tick of flight",
              near(b.pos.z, expected_z, 1e-9) and near(b.pos.x, 0.0, 1e-12),
              f"{b.pos} expected z={expected_z:.6f}")


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


# --- Task 6: flight, respawn, swept collision, earliest hit -----------------
def scenario_flight(d: Diagnostics) -> None:
    print("\n[flight: constant speed, straight, no bounce]")
    sim = boot_to_active()
    place(sim, 2, 5.0, 6.0)  # keep the opponent out of the lane
    launch_ball(sim, "b1", 0.0, -5.0, 0.0, 12.0, shooter_team=1)
    before = ball(sim, "b1").pos
    sim.step(0)
    after = ball(sim, "b1").pos
    d.observe(
        "one tick advances the ball by velocity * dt",
        near(after.z - before.z, 12.0 * K.DT, 1e-12) and near(after.x, 0.0, 1e-12),
        f"dz={after.z - before.z:.6f} expected {12.0 * K.DT:.6f}",
    )

    for _ in range(29):
        sim.step(0)
    b = ball(sim, "b1")
    d.observe(
        "velocity never changes in flight",
        (b.velocity.x, b.velocity.z) == (0.0, 12.0),
        str(b.velocity),
    )
    d.observe(
        "30 ticks travel exactly 30 * v * dt in a straight line",
        near(b.pos.z, -5.0 + 30 * 12.0 * K.DT, 1e-9) and near(b.pos.x, 0.0, 1e-12),
        f"{b.pos} expected z={-5.0 + 30 * 12.0 * K.DT:.6f}",
    )
    d.observe("a travelling ball reports its shooter team", b.shooter_team == 1)
    d.observe("a flying ball has no owner_team", b.owner_team is None)


def scenario_wall_respawn(d: Diagnostics) -> None:
    print("\n[respawn: court exit and the 1 second delay]")
    sim = boot_to_active()
    place(sim, 2, 5.0, 6.0)
    launch_ball(sim, "b1", 0.0, 8.0, 0.0, 14.0, shooter_team=1)

    ticks = 0
    while ball(sim, "b1").mode == "flying" and ticks < 30:
        sim.step(0)
        ticks += 1
    b = ball(sim, "b1")
    d.observe("leaving the court starts a respawn", b.mode == "respawning", b.mode)
    d.observe("no bounce: the ball does not come back into play", b.mode != "flying")
    d.observe(
        "respawn_in_ms is the specified 1000",
        b.respawn_in_ms == K.RESPAWN_MS,
        str(b.respawn_in_ms),
    )
    d.observe(
        "a respawning ball waits at its own original spawn",
        (b.pos.x, b.pos.z) == K.BALL_SPAWNS["b1"],
        str(b.pos),
    )
    d.observe(
        "a respawning ball carries no shooter, owner or velocity",
        b.shooter_team is None
        and b.owner_team is None
        and (b.velocity.x, b.velocity.z) == (0.0, 0.0),
    )

    for _ in range(K.RESPAWN_TICKS - 1):
        sim.step(0)
    d.observe(
        "still respawning one tick short of the full second",
        ball(sim, "b1").mode == "respawning",
        ball(sim, "b1").mode,
    )
    sim.step(0)
    b = ball(sim, "b1")
    d.observe(
        f"grounded again after exactly {K.RESPAWN_TICKS} ticks", b.mode == "ground", b.mode
    )
    d.observe(
        "respawns at its original spawn", (b.pos.x, b.pos.z) == K.BALL_SPAWNS["b1"], str(b.pos)
    )
    d.observe("respawn_in_ms returns to zero", b.respawn_in_ms == 0, str(b.respawn_in_ms))


def scenario_expiry_respawn(d: Diagnostics) -> None:
    print("\n[respawn: 2 second flight lifetime]")
    # Thrown from the back wall at the minimum speed, a ball runs out its
    # lifetime (16 m) before reaching the far wall, which is the only way to
    # observe expiry rather than a court exit.
    sim = boot_to_active()
    place(sim, 1, 0.0, K.T1_Z_MIN)
    place(sim, 2, 5.0, 6.0)
    launch_ball(sim, "b1", 0.0, K.T1_Z_MIN + K.THROW_OFFSET, 0.0, 8.0, shooter_team=1)

    for _ in range(K.FLIGHT_TICKS - 1):
        sim.step(0)
    b = ball(sim, "b1")
    d.observe(
        "still flying one tick before the 2 second lifetime", b.mode == "flying", b.mode
    )
    d.observe("and still inside the court, so this is expiry not a wall", abs(b.pos.z) < K.COURT_Z,
              f"z={b.pos.z:.4f}")
    sim.step(0)
    d.observe(
        f"lifetime expiry at exactly {K.FLIGHT_TICKS} ticks starts a respawn",
        ball(sim, "b1").mode == "respawning",
        ball(sim, "b1").mode,
    )


def scenario_collision(d: Diagnostics) -> None:
    print("\n[collision: swept circles against the opponent only]")

    # A real throw at the maximum legal speed.
    sim = boot_to_active()
    place(sim, 1, 0.0, -3.0)
    place(sim, 2, 0.0, 3.0)
    launch_ball(sim, "b1", 0.0, -2.0, 0.0, 14.0, shooter_team=1)
    step_until_result(sim)
    s = sim.snapshot()
    d.observe(
        "a ball at the maximum legal speed hits the opposing character",
        s.result is not None and s.result.reason == "hit",
        str(s.result),
    )
    d.observe("the hit names the shooter", s.result is not None and s.result.winner == 1)
    d.observe("the hit names the victim", s.result is not None and s.result.victim_team == 2)
    d.observe("the hit names the ball", s.result is not None and s.result.hit_ball_id == "b1")
    gap = 3.0 - ball(sim, "b1").pos.z
    d.observe(
        "impact is caught at the combined radius, never past the centre",
        gap > 0.0,
        f"ball stopped {gap:.4f} m short of the character centre",
    )
    d.note(f"combined radius {K.COMBINED_RADIUS} m, one tick of travel {14.0 * K.DT:.4f} m")

    # The swept solver, not a per-tick overlap sample.
    sim = boot_to_active()
    place(sim, 1, 0.0, -3.0)
    place(sim, 2, 0.0, 3.0)
    # 10 m per tick, far more than the 0.60 m combined radius: both tick
    # endpoints sit clear of the character, so only a swept test finds this.
    launch_ball(sim, "b1", 0.0, -3.0, 0.0, 600.0, shooter_team=1)
    sim.step(0)
    s = sim.snapshot()
    d.observe(
        "a ball crossing the character within one tick still hits (no tunnelling)",
        s.result is not None and s.result.reason == "hit",
        str(s.result),
    )
    d.observe(
        "and its tick endpoints really were both clear of the character",
        abs(-3.0 - 3.0) > K.COMBINED_RADIUS and abs(7.0 - 3.0) > K.COMBINED_RADIUS,
    )

    # A moving target: the character's own movement segment is swept too.
    sim = boot_to_active()
    place(sim, 1, 0.0, -3.0)
    place(sim, 2, 0.0, 1.0)
    launch_ball(sim, "b1", 0.0, -2.0, 0.0, 14.0, shooter_team=1)
    ordinal = sim._last_ordinal + 1  # noqa: SLF001
    member = legs_member(sim, 2)
    epoch = sim.snapshot().epoch
    ticks = 0
    while sim.snapshot().result is None and ticks < 60:
        sim.apply_input(
            member,
            LegsCommand(seq=ordinal, epoch=epoch, move=Vec2(0.0, 1.0)),
            received_ms=0,
            ordinal=ordinal,
        )
        ordinal += 1
        sim.step(0)
        ticks += 1
    d.observe(
        "a character retreating from the ball is still hit on its swept segment",
        sim.snapshot().result is not None,
        str(sim.snapshot().result),
    )

    # Only the opposing character can be hit.
    sim = boot_to_active()
    place(sim, 1, 0.0, -3.0)
    place(sim, 2, 5.0, 6.0)
    launch_ball(sim, "b1", 0.0, -3.0, 0.0, 8.0, shooter_team=1)  # on top of its thrower
    for _ in range(5):
        sim.step(0)
    d.observe(
        "a ball never hits its own thrower",
        sim.snapshot().result is None,
        str(sim.snapshot().result),
    )

    # Grounded and respawning balls damage nobody.
    sim = boot_to_active()
    place(sim, 2, 0.0, 3.0)
    put_ball(sim, "b1", 0.0, 3.0)
    for _ in range(5):
        sim.step(0)
    d.observe("a grounded ball damages nobody", sim.snapshot().result is None)

    sim = boot_to_active()
    place(sim, 2, 0.0, 3.0)
    park_respawning(sim, "b1", 0.0, 3.0)
    for _ in range(5):
        sim.step(0)
    d.observe("a respawning ball damages nobody", sim.snapshot().result is None)

    # A held ball cannot shield its holder.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1", "b2"))
    place(sim, 1, 0.0, -3.0)
    place(sim, 2, 0.0, 3.0)
    put_ball(sim, "b2", 0.0, 3.0)
    Hands(sim, 2).send("press").step()
    d.observe(
        "the holder really is carrying the ball between them and the throw",
        character(sim, 2).held_ball_id == "b2",
        str(character(sim, 2).held_ball_id),
    )
    launch_ball(sim, "b1", 0.0, -2.0, 0.0, 14.0, shooter_team=1)
    step_until_result(sim)
    s = sim.snapshot()
    d.observe(
        "a held ball does not block a throw",
        s.result is not None and s.result.hit_ball_id == "b1",
        str(s.result),
    )

    # A hit at or before the clipped wall endpoint counts.
    sim = boot_to_active()
    place(sim, 2, 0.0, K.T2_Z_MAX)  # hard against the back wall
    launch_ball(sim, "b1", 0.0, 7.9, 0.0, 600.0, shooter_team=1)
    sim.step(0)
    s = sim.snapshot()
    d.observe(
        "a hit before the wall endpoint counts as a hit, not a respawn",
        s.result is not None and s.result.reason == "hit",
        str(s.result),
    )
    d.observe(
        "the hit ball is not respawned in the deciding tick",
        ball(sim, "b1").mode == "flying",
        ball(sim, "b1").mode,
    )


def scenario_earliest_hit(d: Diagnostics) -> None:
    print("\n[hit resolution: earliest, ties by ball ID, opposing draw]")

    # Earliest impact decides, even when a higher ball ID gets there first.
    sim = boot_to_active()
    place(sim, 1, 0.0, -3.0)
    place(sim, 2, 0.0, 3.0)
    launch_ball(sim, "b1", 0.0, -5.0, 0.0, 10.0, shooter_team=1)  # far
    launch_ball(sim, "b2", 0.0, 1.0, 0.0, 10.0, shooter_team=1)  # near
    step_until_result(sim)
    s = sim.snapshot()
    d.observe(
        "the earliest impact decides, not the lowest ball ID",
        s.result is not None and s.result.hit_ball_id == "b2",
        str(s.result),
    )

    # Equal impact times break by ball ID.
    sim = boot_to_active()
    place(sim, 1, 0.0, -3.0)
    place(sim, 2, 0.0, 3.0)
    launch_ball(sim, "b1", 0.5, -1.0, 0.0, 10.0, shooter_team=1)
    launch_ball(sim, "b2", -0.5, -1.0, 0.0, 10.0, shooter_team=1)  # mirror image
    step_until_result(sim)
    s = sim.snapshot()
    d.observe(
        "equal impact times break by ball ID",
        s.result is not None and s.result.hit_ball_id == "b1",
        str(s.result),
    )
    d.observe("a tie on one victim is still a scoring hit",
              s.result is not None and s.result.reason == "hit", str(s.result))

    # Two opposing hits at the same instant are a draw.
    sim = boot_to_active()
    place(sim, 1, 0.0, -3.0)
    place(sim, 2, 0.0, 3.0)
    launch_ball(sim, "b1", 0.0, -1.0, 0.0, 10.0, shooter_team=1)
    launch_ball(sim, "b2", 0.0, 1.0, 0.0, -10.0, shooter_team=2)  # mirror image
    step_until_result(sim)
    s = sim.snapshot()
    d.observe(
        "two opposing hits within 1e-9 are a draw",
        s.result is not None and s.result.reason == "simultaneous",
        str(s.result),
    )
    d.observe("a draw names no winner", s.result is not None and s.result.winner is None)
    d.observe(
        "a draw names no victim and no ball",
        s.result is not None
        and s.result.victim_team is None
        and s.result.hit_ball_id is None,
    )
    d.observe(
        "a draw awards no point", s.score.t1 == 0 and s.score.t2 == 0, str(s.score)
    )


def scenario_round_decided(d: Diagnostics) -> None:
    print("\n[a decided round ignores everything after it]")
    sim = boot_to_active()
    place(sim, 1, 0.0, -3.0)
    place(sim, 2, 0.0, 3.0)
    launch_ball(sim, "b1", 0.0, -2.0, 0.0, 14.0, shooter_team=1)
    launch_ball(sim, "b3", 0.0, 2.0, 0.0, 14.0, shooter_team=1)  # would hit later
    step_until_result(sim)
    decided = sim.snapshot().result
    d.observe("a hit is resolved", decided is not None, str(decided))
    d.observe(
        "the nearer ball decided it", decided is not None and decided.hit_ball_id == "b3",
        str(decided),
    )

    tick_before = sim.snapshot().tick
    remaining_before = sim.snapshot().remaining_ms
    for _ in range(10):
        sim.step(0)
    s = sim.snapshot()
    d.observe("later hit candidates are ignored", s.result == decided, str(s.result))
    d.observe(
        "the round clock stops at the decided tick, it does not drain on",
        s.remaining_ms == remaining_before,
        f"{s.remaining_ms} vs {remaining_before}",
    )
    d.observe(
        "tick still advances once per step after the round is decided",
        s.tick == tick_before + 10,
        f"{s.tick} vs {tick_before + 10}",
    )
    d.observe("no command changes a decided round", s.result == decided)
    d.observe(
        "a decided round has left active for round_end",
        s.phase == "round_end",
        s.phase,
    )

    # A lobby reset clears the result and re-arms the arena. Reset clears the
    # ready set, so readiness has to be supplied again before start, exactly as
    # a real lobby would.
    sim.control("reset")
    ready_all(sim)
    sim.control("start")
    s = sim.snapshot()
    d.observe("a new round clears the result", s.result is None, str(s.result))
    d.observe("a new round re-grounds all four balls",
              all(b.mode == "ground" for b in s.balls))
    d.observe(
        "a new round restores all four ball spawns",
        all((b.pos.x, b.pos.z) == K.BALL_SPAWNS[b.ball_id] for b in s.balls),
    )


# --- Task 7: round and match lifecycle --------------------------------------
def scenario_round_end(d: Diagnostics) -> None:
    print("\n[round_end: one point, result held for 2 seconds]")
    sim = boot_to_active()
    epoch_before = sim.snapshot().epoch
    sim.drain_events()
    win_round(sim, team=1)
    s = sim.snapshot()
    events = sim.drain_events()

    d.observe("a hit enters round_end", s.phase == "round_end", s.phase)
    d.observe("a hit awards exactly one point", (s.score.t1, s.score.t2) == (1, 0),
              f"{s.score.t1}-{s.score.t2}")
    d.observe("the result names the hit", s.result is not None and s.result.reason == "hit",
              str(s.result))
    d.observe("phase_remaining_ms is the specified 2000",
              s.phase_remaining_ms == 2000, str(s.phase_remaining_ms))
    d.observe("the phase transition increments epoch", s.epoch > epoch_before,
              f"{epoch_before} -> {s.epoch}")
    d.observe("round_end clears held balls",
              all(c.held_ball_id is None for c in s.characters))
    d.observe("round_end does NOT reset the arena yet, so the result stays readable",
              any(b.mode == "flying" for b in s.balls),
              str([b.mode for b in s.balls]))
    d.observe("the transition is published as a phase change",
              [n for n, _ in event_epochs(events)] == ["phase:round_end"],
              str(event_epochs(events)))

    # The result display runs exactly 2 seconds, then roles swap.
    ticks = run_out_phase(sim, "round_end")
    d.observe(f"round_end lasts exactly {K.RESULT_TICKS} ticks", ticks == K.RESULT_TICKS,
              str(ticks))
    d.observe("round_end hands over to role_switch",
              sim.snapshot().phase == "role_switch", sim.snapshot().phase)
    d.observe("role_switch resets the arena",
              all(b.mode == "ground" for b in sim.snapshot().balls)
              and all((b.pos.x, b.pos.z) == K.BALL_SPAWNS[b.ball_id]
                      for b in sim.snapshot().balls))
    d.observe("role_switch restores both spawns",
              [(c.pos.x, c.pos.z) for c in sim.snapshot().characters]
              == [K.T1_SPAWN, K.T2_SPAWN],
              str([(c.pos.x, c.pos.z) for c in sim.snapshot().characters]))
    d.observe("role_switch has no phase timer: it waits on readiness",
              sim.snapshot().phase_remaining_ms is None,
              str(sim.snapshot().phase_remaining_ms))
    d.observe("the result persists through role_switch",
              sim.snapshot().result is not None, str(sim.snapshot().result))


def scenario_score_once(d: Diagnostics) -> None:
    print("\n[scoring: exactly once per round]")
    sim = boot_to_active()
    win_round(sim, team=1)
    d.observe("one point after the hit", sim.snapshot().score.t1 == 1,
              str(sim.snapshot().score.t1))

    # Sitting in round_end must not re-score, and neither must role_switch.
    run_out_phase(sim, "round_end")
    d.observe("round_end does not score again", sim.snapshot().score.t1 == 1,
              str(sim.snapshot().score.t1))
    for _ in range(200):
        sim.step(0)
    d.observe("waiting in role_switch does not score again",
              sim.snapshot().score.t1 == 1, str(sim.snapshot().score.t1))

    ready_all(sim)
    run_out_phase(sim, "role_switch")
    run_out_phase(sim, "countdown")
    d.observe("the next round starts from the same score",
              (sim.snapshot().score.t1, sim.snapshot().score.t2) == (1, 0),
              f"{sim.snapshot().score.t1}-{sim.snapshot().score.t2}")
    d.observe("the next round is active", sim.snapshot().phase == "active",
              sim.snapshot().phase)
    d.observe("the next round number is 2", sim.snapshot().round == 2,
              str(sim.snapshot().round))
    d.observe("the next round has the full timer",
              sim.snapshot().remaining_ms == K.ROUND_MS,
              str(sim.snapshot().remaining_ms))
    d.observe("the next round clears the previous result",
              sim.snapshot().result is None, str(sim.snapshot().result))

    # A draw awards nothing to either side.
    sim = boot_to_active()
    draw_round(sim)
    s = sim.snapshot()
    d.observe("a simultaneous draw awards no point",
              (s.score.t1, s.score.t2) == (0, 0), f"{s.score.t1}-{s.score.t2}")
    d.observe("a draw still enters round_end", s.phase == "round_end", s.phase)


def scenario_timeout(d: Diagnostics) -> None:
    print("\n[timeout: the exact 3600-tick boundary]")
    sim = boot_to_active()
    for _ in range(K.ROUND_TICKS):
        sim.step(0)
    s = sim.snapshot()
    d.observe(f"still active after exactly {K.ROUND_TICKS} ticks",
              s.phase == "active", s.phase)
    d.observe("the clock reads zero at that point", s.remaining_ms == 0,
              str(s.remaining_ms))
    d.observe("no result yet", s.result is None, str(s.result))

    sim.step(0)
    s = sim.snapshot()
    d.observe("the next tick ends the round as a timeout",
              s.result is not None and s.result.reason == "timeout", str(s.result))
    d.observe("a timeout awards no point", (s.score.t1, s.score.t2) == (0, 0),
              f"{s.score.t1}-{s.score.t2}")
    d.observe("a timeout names no winner or victim",
              s.result is not None and s.result.winner is None
              and s.result.victim_team is None and s.result.hit_ball_id is None)
    d.observe("a timeout enters round_end", s.phase == "round_end", s.phase)

    # 02: a throw arriving at the deadline is ineligible, but a hit during the
    # last valid step counts. Land one on tick 3600 exactly.
    sim = boot_to_active()
    for _ in range(K.ROUND_TICKS - 1):
        sim.step(0)
    place(sim, 1, 0.0, -3.0)
    place(sim, 2, 0.0, 3.0)
    launch_ball(sim, "b1", 0.0, 2.3, 0.0, 14.0, shooter_team=1)  # hits immediately
    sim.step(0)
    s = sim.snapshot()
    d.observe("a hit on the last valid step counts as a hit, not a timeout",
              s.result is not None and s.result.reason == "hit", str(s.result))
    d.observe("and it scores", (s.score.t1, s.score.t2) == (1, 0),
              f"{s.score.t1}-{s.score.t2}")

    # Input arriving after the round has ended is refused.
    stale_epoch = s.epoch - 1
    try:
        sim.apply_input(
            legs_member(sim, 1),
            LegsCommand(seq=9999, epoch=stale_epoch, move=Vec2(0.0, 1.0)),
            received_ms=0,
            ordinal=9999,
        )
        refused = "accepted"
    except SimulationError as exc:
        refused = exc.code
    d.observe("a command from the ended round is refused",
              refused in ("STALE_EPOCH", "INVALID_PHASE"), refused)

    # 02: "a throw received at the deadline is ineligible". The timeout is
    # decided at tick start, BEFORE queued commands are accepted, so a release
    # that arrives on the deadline tick never launches.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -4.0)
    put_ball(sim, "b1", 0.0, -4.0)
    hands = Hands(sim, 1).send("press").step()
    d.observe("a ball is held going into the deadline",
              character(sim, 1).held_ball_id == "b1",
              str(character(sim, 1).held_ball_id))
    while sim.snapshot().remaining_ms > 0:
        place(sim, 1, 0.0, -4.0)
        sim.step(0)
    d.observe("the clock is exhausted but the round has not ended yet",
              sim.snapshot().phase == "active" and sim.snapshot().result is None,
              sim.snapshot().phase)
    hands.send("release", strength=1.0)  # queued on the deadline tick
    sim.step(0)
    s = sim.snapshot()
    d.observe("a release queued at the deadline does not launch",
              ball(sim, "b1").mode != "flying", ball(sim, "b1").mode)
    d.observe("and the round still ends as a timeout draw",
              s.result is not None and s.result.reason == "timeout"
              and (s.score.t1, s.score.t2) == (0, 0), str(s.result))


def scenario_role_swap(d: Diagnostics) -> None:
    print("\n[role swap: after EVERY round, including draws]")

    for label, finish in (("a hit", lambda s: win_round(s, 1)),
                          ("a draw", draw_round)):
        sim = boot_to_active()
        before = assignment_map(sim)
        version_before = sim.snapshot().assignment_version
        finish(sim)
        sim.drain_events()
        run_out_phase(sim, "round_end")
        after = assignment_map(sim)
        events = sim.drain_events()

        swapped = (
            after[(1, "arms")] == before[(1, "legs")]
            and after[(1, "legs")] == before[(1, "arms")]
            and after[(2, "arms")] == before[(2, "legs")]
            and after[(2, "legs")] == before[(2, "arms")]
        )
        d.observe(f"{label} swaps arms and legs within each team", swapped,
                  f"{before} -> {after}")
        d.observe(f"{label} keeps every phone on its own team",
                  {m for (t, _), m in before.items() if t == 1}
                  == {m for (t, _), m in after.items() if t == 1},
                  str(after))
        d.observe(f"{label} increments assignment_version",
                  sim.snapshot().assignment_version == version_before + 1,
                  f"{version_before} -> {sim.snapshot().assignment_version}")
        labels = [n for n, _ in event_epochs(events)]
        d.observe(f"{label} publishes phase.changed then roles.changed",
                  labels == ["phase:role_switch", "roles"], str(labels))
        epochs = [e for _, e in event_epochs(events)]
        d.observe(f"{label} never regresses epoch across the bundle",
                  epochs == sorted(epochs), str(epochs))


def scenario_readiness_gate(d: Diagnostics) -> None:
    print("\n[readiness gates the next round]")
    sim = boot_to_active()
    win_round(sim, team=1)
    run_out_phase(sim, "round_end")
    d.observe("role_switch reached", sim.snapshot().phase == "role_switch",
              sim.snapshot().phase)

    # The swap cleared readiness, so nothing may start.
    for _ in range(300):
        sim.step(0)
    d.observe("role_switch waits indefinitely without readiness",
              sim.snapshot().phase == "role_switch", sim.snapshot().phase)

    # Three of four ready is not enough: never force-start an unready phone.
    # Everyone is still connected with a screen present, so this is a pure
    # readiness wait and NOT a device loss — role_switch holds rather than
    # aborting. The device-loss cases live in scenario_device_guard, because in
    # a non-lobby phase 02 makes them resets, not waits.
    for ready_subset in (frozenset({P1, P2, P3}), frozenset({P1}), frozenset()):
        sim.set_readiness(
            ready_member_ids=ready_subset,
            connected_member_ids=frozenset({P1, P2, P3, P4}),
            screen_count=1,
            host_connected=True,
        )
        sim.step(0)
        d.observe(
            f"{len(ready_subset)} of four ready keeps role_switch waiting",
            sim.snapshot().phase == "role_switch",
            sim.snapshot().phase,
        )

    # All four ready, connected, with a screen: the NEXT step begins the round.
    ready_all(sim)
    d.observe("set_readiness alone does not change phase",
              sim.snapshot().phase == "role_switch", sim.snapshot().phase)
    sim.step(0)
    s = sim.snapshot()
    d.observe("the step after readiness enters countdown", s.phase == "countdown", s.phase)
    d.observe("countdown shows the specified 3000 ms", s.phase_remaining_ms == 3000,
              str(s.phase_remaining_ms))
    d.observe("the new round number is 2", s.round == 2, str(s.round))
    d.observe("countdown clears the previous result", s.result is None, str(s.result))
    ticks = run_out_phase(sim, "countdown")
    d.observe(f"countdown lasts exactly {K.COUNTDOWN_TICKS} ticks",
              ticks == K.COUNTDOWN_TICKS, str(ticks))
    d.observe("countdown hands over to active", sim.snapshot().phase == "active",
              sim.snapshot().phase)


def scenario_first_to_three(d: Diagnostics) -> None:
    print("\n[first to three: winning-round swap and match_end]")
    sim = boot_to_active()
    for round_number in (1, 2):
        win_round(sim, team=1)
        d.observe(f"round {round_number} scores for team 1",
                  sim.snapshot().score.t1 == round_number,
                  str(sim.snapshot().score.t1))
        d.observe(f"round {round_number} does not end the match",
                  sim.snapshot().winner is None, str(sim.snapshot().winner))
        advance_to_next_active(sim)

    # The deciding round.
    before = assignment_map(sim)
    win_round(sim, team=1)
    d.observe("the third point is scored", sim.snapshot().score.t1 == 3,
              str(sim.snapshot().score.t1))
    d.observe("the match does not end until the result has been shown",
              sim.snapshot().phase == "round_end", sim.snapshot().phase)
    sim.drain_events()
    run_out_phase(sim, "round_end")
    s = sim.snapshot()
    events = sim.drain_events()

    d.observe("the match ends at match_end", s.phase == "match_end", s.phase)
    d.observe("the winner is team 1", s.winner == 1, str(s.winner))
    d.observe("the final score is 3-0", (s.score.t1, s.score.t2) == (3, 0),
              f"{s.score.t1}-{s.score.t2}")
    d.observe("match_end retains the deciding result",
              s.result is not None and s.result.reason == "hit", str(s.result))
    d.observe("match_end has no phase timer", s.phase_remaining_ms is None,
              str(s.phase_remaining_ms))

    after = assignment_map(sim)
    d.observe(
        "the winning round still swaps roles",
        after[(1, "arms")] == before[(1, "legs")]
        and after[(2, "arms")] == before[(2, "legs")],
        f"{before} -> {after}",
    )
    labels = [n for n, _ in event_epochs(events)]
    d.observe("the winning bundle is role_switch, roles, then match_end",
              labels == ["phase:role_switch", "roles", "phase:match_end"], str(labels))
    epochs = [e for _, e in event_epochs(events)]
    d.observe("the winning bundle never regresses epoch", epochs == sorted(epochs),
              str(epochs))

    # match_end holds; it does not wander into another round.
    for _ in range(300):
        sim.step(0)
    d.observe("match_end holds without readiness", sim.snapshot().phase == "match_end",
              sim.snapshot().phase)
    ready_all(sim)
    for _ in range(10):
        sim.step(0)
    d.observe("match_end does not restart even when every phone readies",
              sim.snapshot().phase == "match_end", sim.snapshot().phase)
    d.observe("match_end keeps the winner", sim.snapshot().winner == 1,
              str(sim.snapshot().winner))

    # Draws do not end a match, so all-draw play continues (02 accepts this).
    sim2 = boot_to_active()
    for _ in range(4):
        draw_round(sim2)
        advance_to_next_active(sim2)
    s2 = sim2.snapshot()
    d.observe("four draws award nothing and the match continues",
              (s2.score.t1, s2.score.t2) == (0, 0) and s2.winner is None,
              f"{s2.score.t1}-{s2.score.t2} winner {s2.winner}")
    d.observe("and the round number has advanced to 5", s2.round == 5, str(s2.round))


def scenario_full_match(d: Diagnostics) -> None:
    print("\n[a complete match through the real seam]")
    sim = boot_to_active()
    start_map = assignment_map(sim)
    violations: list[str] = []
    epochs: list[int] = []
    ticks: list[int] = []
    role_history: list[dict[tuple[int, str], str]] = []

    def audit(where: str) -> None:
        s = sim.snapshot()
        ticks.append(s.tick)
        if [c.team for c in s.characters] != [1, 2]:
            violations.append(f"{where}: characters")
        if [b.ball_id for b in s.balls] != list(K.BALL_IDS):
            violations.append(f"{where}: balls")
        for b in s.balls:
            if (b.owner_team is not None) != (b.mode == "held"):
                violations.append(f"{where}: owner_team on {b.ball_id}")
            if (b.shooter_team is not None) != (b.mode == "flying"):
                violations.append(f"{where}: shooter_team on {b.ball_id}")
            if (b.respawn_in_ms != 0) != (b.mode == "respawning"):
                violations.append(f"{where}: respawn_in_ms on {b.ball_id}")
            if b.mode != "flying" and (b.velocity.x or b.velocity.z):
                violations.append(f"{where}: velocity on {b.ball_id}")
        if s.phase_remaining_ms is not None and s.phase not in ("countdown", "round_end"):
            violations.append(f"{where}: phase_remaining_ms in {s.phase}")
        if s.winner is not None and s.phase != "match_end":
            violations.append(f"{where}: winner in {s.phase}")
        if len(s.assignments) != 4:
            violations.append(f"{where}: assignments")
        if not 0 <= s.remaining_ms <= K.ROUND_MS:
            violations.append(f"{where}: remaining_ms {s.remaining_ms}")
        epochs.extend(e for _, e in event_epochs(sim.drain_events()))

    # Team 1 takes three rounds, with a draw in the middle for good measure.
    audit("active round 1")
    for finisher in (lambda: win_round(sim, 1), lambda: draw_round(sim),
                     lambda: win_round(sim, 1), lambda: win_round(sim, 1)):
        finisher()
        audit("round_end")
        run_out_phase(sim, "round_end")
        audit("after result display")
        role_history.append(assignment_map(sim))
        if sim.snapshot().phase == "role_switch":
            ready_all(sim)
            run_out_phase(sim, "role_switch")
            audit("countdown")
            run_out_phase(sim, "countdown")
            audit("active")

    s = sim.snapshot()
    d.observe("a full match reaches a winner", s.phase == "match_end", s.phase)
    d.observe("the winner is the team with three points",
              s.winner == 1 and s.score.t1 == 3, f"winner {s.winner} score {s.score.t1}")
    d.observe("the draw cost nobody a point", s.score.t2 == 0, str(s.score.t2))
    d.observe("four rounds were played", s.round == 4, str(s.round))
    d.observe("no state invariant was broken at any boundary",
              not violations, "; ".join(violations[:4]))
    d.observe("epoch never regressed across the whole match",
              epochs == sorted(epochs), str(epochs))
    d.observe("tick never reset across the whole match",
              all(b >= a for a, b in zip(ticks, ticks[1:])), str(ticks[:6]))

    # Rematch is the only way out of match_end. Formally task 8, but match_end
    # only became reachable here, so its one exit is checked now.
    final_map = assignment_map(sim)
    sim.control("rematch")
    s = sim.snapshot()
    d.observe("rematch returns to lobby", s.phase == "lobby", s.phase)
    d.observe("rematch resets the score", (s.score.t1, s.score.t2) == (0, 0),
              f"{s.score.t1}-{s.score.t2}")
    d.observe("rematch clears the winner and result",
              s.winner is None and s.result is None, f"{s.winner} {s.result}")
    d.observe("rematch retains the final assignments",
              assignment_map(sim) == final_map, str(assignment_map(sim)))
    d.observe("rematch resets the arena",
              all(b.mode == "ground" for b in s.balls)
              and all((b.pos.x, b.pos.z) == K.BALL_SPAWNS[b.ball_id] for b in s.balls))
    d.observe("rematch requires readiness again before a new match",
              s.round == 0, str(s.round))
    ready_all(sim)
    sim.control("start")
    d.observe("a fresh match starts after rematch",
              sim.snapshot().phase == "countdown" and sim.snapshot().round == 1,
              f"{sim.snapshot().phase} round {sim.snapshot().round}")
    d.note(f"assignments after a four-round match: {final_map}")
    # 05 H8-10 gate: both teammates use both roles. Over the match each phone
    # must have occupied arms AND legs at some point.
    roles_held: dict[str, set[str]] = {}
    for mapping in [start_map] + role_history:
        for (_, role), member_id in mapping.items():
            roles_held.setdefault(member_id, set()).add(role)
    d.observe(
        "every phone occupied both roles during the match",
        all(held == {"arms", "legs"} for held in roles_held.values())
        and len(roles_held) == 4,
        str({m: sorted(r) for m, r in roles_held.items()}),
    )


# --- Task 8: abort to lobby, device guard, reset and rematch ----------------
def lobby_reset_observations(d: Diagnostics, sim: Simulation, label: str,
                            epoch_before: int, assignments_before,
                            version_before: int) -> None:
    """Check every clause 02 requires of a reset/abort to lobby."""
    s = sim.snapshot()
    d.observe(f"{label}: phase is lobby", s.phase == "lobby", s.phase)
    d.observe(f"{label}: score cleared", (s.score.t1, s.score.t2) == (0, 0),
              f"{s.score.t1}-{s.score.t2}")
    d.observe(f"{label}: round cleared", s.round == 0, str(s.round))
    d.observe(f"{label}: timer restored", s.remaining_ms == K.ROUND_MS,
              str(s.remaining_ms))
    d.observe(f"{label}: result and winner cleared",
              s.result is None and s.winner is None, f"{s.result} {s.winner}")
    d.observe(f"{label}: epoch incremented", s.epoch > epoch_before,
              f"{epoch_before} -> {s.epoch}")
    d.observe(f"{label}: no held balls", all(c.held_ball_id is None
                                             for c in s.characters))
    d.observe(f"{label}: arena reset to spawns",
              all(b.mode == "ground" for b in s.balls)
              and all((b.pos.x, b.pos.z) == K.BALL_SPAWNS[b.ball_id] for b in s.balls)
              and [(c.pos.x, c.pos.z) for c in s.characters] == [K.T1_SPAWN, K.T2_SPAWN])
    d.observe(f"{label}: assignments kept", s.assignments == assignments_before,
              str(s.assignments))
    d.observe(f"{label}: no role swap, so assignment_version is unchanged",
              s.assignment_version == version_before,
              f"{version_before} -> {s.assignment_version}")
    d.observe(f"{label}: phase_remaining_ms null", s.phase_remaining_ms is None,
              str(s.phase_remaining_ms))


def scenario_device_guard(d: Diagnostics) -> None:
    print("\n[device guard: required-device loss aborts to lobby]")

    cases = (
        ("a phone disconnects", dict(ready_member_ids=frozenset({P1, P2, P3, P4}),
                                     connected_member_ids=frozenset({P1, P2, P3}),
                                     screen_count=1, host_connected=True)),
        ("the original host disconnects",
         dict(ready_member_ids=frozenset({P1, P2, P3, P4}),
              connected_member_ids=frozenset({P1, P2, P3, P4}),
              screen_count=1, host_connected=False)),
        ("every screen is lost", dict(ready_member_ids=frozenset({P1, P2, P3, P4}),
                                      connected_member_ids=frozenset({P1, P2, P3, P4}),
                                      screen_count=0, host_connected=True)),
        ("a phone revokes readiness",
         dict(ready_member_ids=frozenset({P1, P2, P3}),
              connected_member_ids=frozenset({P1, P2, P3, P4}),
              screen_count=1, host_connected=True)),
    )

    for label, facts in cases:
        sim = boot_to_active()
        epoch_before = sim.snapshot().epoch
        assignments_before = sim.snapshot().assignments
        version_before = sim.snapshot().assignment_version
        sim.set_readiness(**facts)  # type: ignore[arg-type]
        d.observe(f"{label}: set_readiness alone does not abort",
                  sim.snapshot().phase == "active", sim.snapshot().phase)
        sim.step(0)
        lobby_reset_observations(d, sim, label, epoch_before, assignments_before,
                                 version_before)

    # Losing one screen while another remains is a membership change only.
    sim = boot_to_active()
    sim.set_readiness(
        ready_member_ids=frozenset({P1, P2, P3, P4}),
        connected_member_ids=frozenset({P1, P2, P3, P4}),
        screen_count=1,  # down from 2, but one remains
        host_connected=True,
    )
    for _ in range(10):
        sim.step(0)
    d.observe("losing one screen while another remains does not abort",
              sim.snapshot().phase == "active", sim.snapshot().phase)

    # An aborted round awards no point and triggers no role swap, even when a
    # hit had already been scored in it.
    sim = boot_to_active()
    version_before = sim.snapshot().assignment_version
    win_round(sim, team=1)
    d.observe("a point was scored before the interruption",
              sim.snapshot().score.t1 == 1, str(sim.snapshot().score.t1))
    sim.set_readiness(
        ready_member_ids=frozenset({P1, P2, P3, P4}),
        connected_member_ids=frozenset({P1, P2}),
        screen_count=1,
        host_connected=True,
    )
    sim.step(0)
    s = sim.snapshot()
    d.observe("an aborted round keeps no point", (s.score.t1, s.score.t2) == (0, 0),
              f"{s.score.t1}-{s.score.t2}")
    d.observe("an aborted round triggers no role swap",
              s.assignment_version == version_before,
              f"{version_before} -> {s.assignment_version}")

    # The guard fires in every non-lobby phase.
    def reach(phase: str) -> Simulation:
        sim = boot_to_active()
        if phase == "countdown":
            win_round(sim, 1)
            run_out_phase(sim, "round_end")
            ready_all(sim)
            sim.step(0)
        elif phase == "round_end":
            win_round(sim, 1)
        elif phase == "role_switch":
            win_round(sim, 1)
            run_out_phase(sim, "round_end")
        elif phase == "match_end":
            for _ in range(2):
                win_round(sim, 1)
                advance_to_next_active(sim)
            win_round(sim, 1)
            run_out_phase(sim, "round_end")
        return sim

    for phase in ("countdown", "active", "round_end", "role_switch", "match_end"):
        sim = reach(phase)
        d.observe(f"reached {phase} for the guard check",
                  sim.snapshot().phase == phase, sim.snapshot().phase)
        sim.set_readiness(
            ready_member_ids=frozenset({P1, P2, P3, P4}),
            connected_member_ids=frozenset({P1, P2, P3}),
            screen_count=1,
            host_connected=True,
        )
        sim.step(0)
        d.observe(f"a disconnect during {phase} aborts to lobby",
                  sim.snapshot().phase == "lobby", sim.snapshot().phase)

    # Readiness revocation aborts ONLY in countdown and active. Elsewhere it
    # just clears that member's readiness.
    for phase, expected in (("countdown", "lobby"), ("active", "lobby"),
                            ("round_end", "round_end"),
                            ("role_switch", "role_switch"),
                            ("match_end", "match_end")):
        sim = reach(phase)
        sim.set_readiness(
            ready_member_ids=frozenset({P1, P2, P3}),
            connected_member_ids=frozenset({P1, P2, P3, P4}),
            screen_count=1,
            host_connected=True,
        )
        sim.step(0)
        d.observe(
            f"ready=false during {phase} -> {expected}",
            sim.snapshot().phase == expected,
            sim.snapshot().phase,
        )

    # No duplicate abort: once in lobby the guard stops, and the adapter's own
    # abort call afterwards is a plain lobby reset rather than a second abort.
    sim = boot_to_active()
    sim.set_readiness(
        ready_member_ids=frozenset({P1, P2, P3, P4}),
        connected_member_ids=frozenset({P1, P2, P3}),
        screen_count=1,
        host_connected=True,
    )
    sim.step(0)
    sim.drain_events()
    for _ in range(20):
        sim.step(0)
    events = sim.drain_events()
    d.observe("the guard does not fire again once in lobby", not events,
              f"{len(events)} further events")
    epoch_before = sim.snapshot().epoch
    sim.control("abort")
    d.observe("a redundant adapter abort is a safe lobby reset",
              sim.snapshot().phase == "lobby"
              and sim.snapshot().epoch == epoch_before + 1,
              f"epoch {epoch_before} -> {sim.snapshot().epoch}")

    # Old-epoch input cannot leak through an abort.
    sim = boot_to_active()
    stale_epoch = sim.snapshot().epoch
    member = legs_member(sim, 1)
    sim.set_readiness(
        ready_member_ids=frozenset({P1, P2, P3, P4}),
        connected_member_ids=frozenset({P1, P2, P3}),
        screen_count=1,
        host_connected=True,
    )
    sim.step(0)
    try:
        sim.apply_input(
            member,
            LegsCommand(seq=1, epoch=stale_epoch, move=Vec2(0.0, 1.0)),
            received_ms=0,
            ordinal=5000,
        )
        refused = "accepted"
    except SimulationError as exc:
        refused = exc.code
    d.observe("input from before the abort is refused",
              refused in ("STALE_EPOCH", "INVALID_PHASE"), refused)

    # 06's end-to-end script: disconnect a phone while it is holding a ball.
    # The ball must not fly, and the match must reset with readiness cleared.
    sim = boot_to_active()
    clear_ground_balls(sim, ("b1",))
    place(sim, 1, 0.0, -4.0)
    put_ball(sim, "b1", 0.0, -4.0)
    Hands(sim, 1).send("press").step()
    d.observe("a ball is held before the disconnect",
              character(sim, 1).held_ball_id == "b1",
              str(character(sim, 1).held_ball_id))
    sim.set_readiness(
        ready_member_ids=frozenset({P1, P2, P3, P4}),
        connected_member_ids=frozenset({P2, P3, P4}),
        screen_count=1,
        host_connected=True,
    )
    sim.step(0)
    d.observe("disconnecting while holding does not launch the ball",
              ball(sim, "b1").mode == "ground", ball(sim, "b1").mode)
    d.observe("the held ball returns to its spawn with the arena reset",
              (ball(sim, "b1").pos.x, ball(sim, "b1").pos.z) == K.BALL_SPAWNS["b1"],
              str(ball(sim, "b1").pos))

    # A disconnect on the same tick a hit would land: the guard is evaluated
    # first, so the aborted round awards nothing.
    sim = boot_to_active()
    place(sim, 1, 0.0, -3.0)
    place(sim, 2, 0.0, 3.0)
    launch_ball(sim, "b1", 0.0, 2.3, 0.0, 14.0, shooter_team=1)  # would hit next step
    sim.set_readiness(
        ready_member_ids=frozenset({P1, P2, P3, P4}),
        connected_member_ids=frozenset({P1, P2, P3}),
        screen_count=1,
        host_connected=True,
    )
    sim.step(0)
    s = sim.snapshot()
    d.observe("a disconnect beats a hit landing on the same tick",
              s.phase == "lobby" and s.result is None
              and (s.score.t1, s.score.t2) == (0, 0),
              f"{s.phase} {s.result} {s.score.t1}-{s.score.t2}")

    # There is no resume: play restarts from round 1 after re-readying.
    ready_all(sim)
    sim.control("start")
    run_out_phase(sim, "countdown")
    s = sim.snapshot()
    d.observe("after an abort the match restarts at round 1",
              s.round == 1 and s.phase == "active", f"round {s.round} {s.phase}")
    d.observe("and from a zero score", (s.score.t1, s.score.t2) == (0, 0),
              f"{s.score.t1}-{s.score.t2}")

    # Reconnection on its own resumes nothing: a fresh host start is required.
    sim = boot_to_active()
    sim.set_readiness(
        ready_member_ids=frozenset({P1, P2, P3, P4}),
        connected_member_ids=frozenset({P1, P2, P3}),
        screen_count=1,
        host_connected=True,
    )
    sim.step(0)
    ready_all(sim)  # everyone is back and ready again
    for _ in range(120):
        sim.step(0)
    d.observe("reconnecting and re-readying does not resume the match",
              sim.snapshot().phase == "lobby" and sim.snapshot().round == 0,
              f"{sim.snapshot().phase} round {sim.snapshot().round}")

    # Start is refused while a required device is missing.
    for label, facts in (
        ("no screen", dict(ready_member_ids=frozenset({P1, P2, P3, P4}),
                           connected_member_ids=frozenset({P1, P2, P3, P4}),
                           screen_count=0, host_connected=True)),
        ("no host", dict(ready_member_ids=frozenset({P1, P2, P3, P4}),
                         connected_member_ids=frozenset({P1, P2, P3, P4}),
                         screen_count=1, host_connected=False)),
        ("a phone absent", dict(ready_member_ids=frozenset({P1, P2, P3, P4}),
                                connected_member_ids=frozenset({P1, P2, P3}),
                                screen_count=1, host_connected=True)),
        ("a phone unready", dict(ready_member_ids=frozenset({P1, P2, P3}),
                                 connected_member_ids=frozenset({P1, P2, P3, P4}),
                                 screen_count=1, host_connected=True)),
    ):
        fresh = Simulation(FOUR)
        fresh.set_readiness(**facts)  # type: ignore[arg-type]
        try:
            fresh.control("start")
            code = "accepted"
        except SimulationError as exc:
            code = exc.code
        d.observe(f"start refused with {label}", code == "NOT_READY", code)


def scenario_reset_and_rematch(d: Diagnostics) -> None:
    print("\n[reset and rematch]")

    # Host reset performs the same lobby reset from every phase.
    for phase in ("countdown", "active", "round_end", "role_switch", "match_end"):
        sim = boot_to_active()
        if phase == "countdown":
            win_round(sim, 1)
            run_out_phase(sim, "round_end")
            ready_all(sim)
            sim.step(0)
        elif phase == "round_end":
            win_round(sim, 1)
        elif phase == "role_switch":
            win_round(sim, 1)
            run_out_phase(sim, "round_end")
        elif phase == "match_end":
            for _ in range(2):
                win_round(sim, 1)
                advance_to_next_active(sim)
            win_round(sim, 1)
            run_out_phase(sim, "round_end")
        epoch_before = sim.snapshot().epoch
        assignments_before = sim.snapshot().assignments
        version_before = sim.snapshot().assignment_version
        d.observe(f"reset: reached {phase}", sim.snapshot().phase == phase,
                  sim.snapshot().phase)
        sim.control("reset")
        lobby_reset_observations(d, sim, f"reset from {phase}", epoch_before,
                                 assignments_before, version_before)

    # A reset while already in lobby still invalidates the old epoch.
    sim = Simulation(FOUR)
    epoch_before = sim.snapshot().epoch
    sim.control("reset")
    events = sim.drain_events()
    d.observe("a reset in lobby still increments epoch",
              sim.snapshot().epoch == epoch_before + 1,
              f"{epoch_before} -> {sim.snapshot().epoch}")
    d.observe("a reset in lobby still publishes PhaseChanged(lobby)",
              [n for n, _ in event_epochs(events)] == ["phase:lobby"],
              str(event_epochs(events)))

    # Rematch is valid only at match_end.
    for phase in ("lobby", "countdown", "active", "round_end", "role_switch"):
        sim = boot_to_active()
        if phase == "lobby":
            sim.control("reset")
        elif phase == "countdown":
            win_round(sim, 1)
            run_out_phase(sim, "round_end")
            ready_all(sim)
            sim.step(0)
        elif phase == "round_end":
            win_round(sim, 1)
        elif phase == "role_switch":
            win_round(sim, 1)
            run_out_phase(sim, "round_end")
        try:
            sim.control("rematch")
            code = "accepted"
        except SimulationError as exc:
            code = exc.code
        d.observe(f"rematch refused in {phase}", code == "INVALID_PHASE", code)

    # Abort and reset are the same reset, as 03 specifies.
    sim_a, sim_b = boot_to_active(), boot_to_active()
    sim_a.control("abort", reason="transport failure")
    sim_b.control("reset")
    d.observe("abort and reset produce the same lobby state",
              sim_a.snapshot() == sim_b.snapshot(),
              "snapshots differ")
    d.observe("abort accepts a reason without needing it in state",
              sim_a.snapshot().phase == "lobby")

    # An unknown control action is refused.
    sim = boot_to_active()
    try:
        sim.control("pause")  # type: ignore[arg-type]
        code = "accepted"
    except SimulationError as exc:
        code = exc.code
    d.observe("an unknown control action is refused", code == "INVALID_INPUT", code)


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

    # Possession: Team 1 holds the nearest ball, which rides on its centre.
    sim = boot_to_active()
    place(sim, 1, 0.0, -3.0)
    put_ball(sim, "b1", 0.4, -3.0)
    Hands(sim, 1).send("press").step()
    fixtures.append(("active-held.json", envelope(sim.snapshot(), 5500)))

    # A real throw in flight, launched through the release path.
    sim = boot_to_active()
    place(sim, 1, 0.0, -3.0)
    put_ball(sim, "b1", 0.4, -3.0)
    hands = Hands(sim, 1).send("press").step()
    place(sim, 1, 0.0, -3.0)
    hands.send("release", strength=0.5).step()
    for _ in range(10):
        sim.step(0)
    fixtures.append(("active-flying.json", envelope(sim.snapshot(), 6000)))

    # Round end after a hit: one point, result visible, 2 second display.
    sim = boot_to_active()
    win_round(sim, team=1)
    fixtures.append(("round-end-hit.json", envelope(sim.snapshot(), 7000)))

    # Role switch: arena reset, roles swapped, waiting on readiness.
    run_out_phase(sim, "round_end")
    fixtures.append(("role-switch.json", envelope(sim.snapshot(), 9000)))

    # Round end after a timeout draw: no point to either side.
    timeout_sim = boot_to_active()
    for _ in range(K.ROUND_TICKS + 1):
        timeout_sim.step(0)
    fixtures.append(("round-end-timeout.json", envelope(timeout_sim.snapshot(), 70000)))

    # Match end: winner and final score.
    won = boot_to_active()
    for _ in range(2):
        win_round(won, 1)
        advance_to_next_active(won)
    win_round(won, 1)
    run_out_phase(won, "round_end")
    fixtures.append(("match-end-winner.json", envelope(won.snapshot(), 120000)))

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
    print("Tasks 1-8: DTOs, reset state, movement, input defense, acquisition,")
    print("ownership, no-throw zone, flight, respawn, swept collision, scoring,")
    print("timeout draw, round/match lifecycle, role swapping, readiness, and")
    print("abort-to-lobby with the simulation-owned device guard")

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
    scenario_flight(diagnostics)
    scenario_wall_respawn(diagnostics)
    scenario_expiry_respawn(diagnostics)
    scenario_collision(diagnostics)
    scenario_earliest_hit(diagnostics)
    scenario_round_decided(diagnostics)
    scenario_round_end(diagnostics)
    scenario_score_once(diagnostics)
    scenario_timeout(diagnostics)
    scenario_role_swap(diagnostics)
    scenario_readiness_gate(diagnostics)
    scenario_first_to_three(diagnostics)
    scenario_full_match(diagnostics)
    scenario_device_guard(diagnostics)
    scenario_reset_and_rematch(diagnostics)

    total = diagnostics.matched + len(diagnostics.deviations)
    print(f"\n{diagnostics.matched}/{total} observations match the specified rules")
    if diagnostics.deviations:
        print("deviations from spec:")
        for rule in diagnostics.deviations:
            print(f"  - {rule}")
        return 1
    print("\nEvery ordered task through task 8 is implemented. Task 9 is the")
    print("remaining item: run this runner as a full-match diagnostic, then")
    print("the real four-phone integration. Neither adds engine mechanics.")
    print("\nADAPTER NOTE: the device guard reads only set_readiness facts.")
    print("03 clears readiness at swap/reset/abort/rematch, NOT at countdown")
    print("or active entry. Clearing it there aborts every match instantly,")
    print("because ready=true is only legal in lobby/role_switch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
