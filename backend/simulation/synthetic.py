"""Synthetic scenario runner and fixture emitter. No framework imports.

This is the verification vehicle for the simulation: it drives scenarios
through the real Simulation methods and the real command DTOs, with no
alternate control API and no temporary interface to replace later.

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
from .types import ArmsCommand, Assignment, LegsCommand, SimulationError, Vec2

# Readable substitutes for opaque production IDs, as used in 03's examples.
P1, P2, P3, P4 = "p1", "p2", "p3", "p4"

FOUR = (
    Assignment(member_id=P1, team=1, role="arms"),
    Assignment(member_id=P2, team=1, role="legs"),
    Assignment(member_id=P3, team=2, role="arms"),
    Assignment(member_id=P4, team=2, role="legs"),
)

TOL = 1e-9


# --- Tiny check harness (not a test suite: a runner that reports) -----------
class Report:
    def __init__(self) -> None:
        self.passed = 0
        self.failed: list[str] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"  PASS  {name}")
        else:
            self.failed.append(name)
            suffix = f" -- {detail}" if detail else ""
            print(f"  FAIL  {name}{suffix}")

    def close(self, detail: str = "") -> None:
        if detail:
            print(detail)


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
def scenario_reset_snapshot(r: Report) -> None:
    print("\n[reset/lobby snapshot]")
    sim = Simulation(FOUR)
    s = sim.snapshot()

    r.check("lobby phase", s.phase == "lobby", s.phase)
    r.check("tick 0", s.tick == 0)
    r.check("epoch 0", s.epoch == 0)
    r.check("round 0", s.round == 0)
    r.check("score zero", s.score.t1 == 0 and s.score.t2 == 0)
    r.check("remaining_ms 60000", s.remaining_ms == 60000, str(s.remaining_ms))
    r.check("phase_remaining_ms null", s.phase_remaining_ms is None)
    r.check("result null", s.result is None)
    r.check("winner null", s.winner is None)

    r.check("exactly two characters", len(s.characters) == 2, str(len(s.characters)))
    r.check("characters sorted by team", [c.team for c in s.characters] == [1, 2])
    t1, t2 = s.characters
    r.check("T1 spawn (0,-6)", (t1.pos.x, t1.pos.z) == K.T1_SPAWN, str(t1.pos))
    r.check("T2 spawn (0,6)", (t2.pos.x, t2.pos.z) == K.T2_SPAWN, str(t2.pos))
    r.check("T1 aim forward +z", (t1.aim.x, t1.aim.z) == (0.0, 1.0), str(t1.aim))
    r.check("T2 aim forward -z", (t2.aim.x, t2.aim.z) == (0.0, -1.0), str(t2.aim))
    r.check("no held balls", t1.held_ball_id is None and t2.held_ball_id is None)

    r.check("exactly four balls", len(s.balls) == 4, str(len(s.balls)))
    r.check(
        "balls sorted by id",
        [b.ball_id for b in s.balls] == ["b1", "b2", "b3", "b4"],
    )
    spawns_ok = all(
        (b.pos.x, b.pos.z) == K.BALL_SPAWNS[b.ball_id] for b in s.balls
    )
    r.check("all four ball spawns exact", spawns_ok)
    r.check("all balls grounded", all(b.mode == "ground" for b in s.balls))
    r.check(
        "no ownership in lobby",
        all(b.owner_team is None and b.shooter_team is None for b in s.balls),
    )
    r.check(
        "zero velocity and respawn",
        all(
            b.velocity.x == 0 and b.velocity.z == 0 and b.respawn_in_ms == 0
            for b in s.balls
        ),
    )
    r.check("assignment_version 1 for four", s.assignment_version == 1)


def scenario_four_directions(r: Report) -> None:
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
        r.check(
            f"ten moves {name}",
            ok,
            f"moved ({after.x - before.x:.6f},{after.z - before.z:.6f}) "
            f"expected ({dx:.6f},{dz:.6f})",
        )


def scenario_diagonal_speed(r: Report) -> None:
    print("\n[movement: diagonal magnitude capped at 1]")
    sim = boot_to_active()
    before = character(sim, 1).pos
    # A unit diagonal: already magnitude 1, so speed must stay 3.5 m/s.
    inv = 1.0 / math.sqrt(2.0)
    drive(sim, 1, Vec2(inv, inv), 10, ordinal=1)
    after = character(sim, 1).pos
    travelled = math.hypot(after.x - before.x, after.z - before.z)
    expected = 10 * K.MOVE_SPEED * K.DT
    r.check(
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
    r.check(
        "(1,1) magnitude 1.414 rejected as INVALID_INPUT",
        raised,
        "03 allows magnitude <= 1.001 only",
    )

    # A diagonal with in-range components but magnitude just over 1 is the
    # only way to reach the 1.001 tolerance: normalized, not rejected.
    sim3 = boot_to_active()
    edge = 0.7072  # magnitude 1.000136...
    r.check(
        "edge case really is slight excess",
        1.0 < math.hypot(edge, edge) <= K.MOVE_MAGNITUDE_TOLERANCE,
        f"magnitude {math.hypot(edge, edge):.6f}",
    )
    before3 = character(sim3, 1).pos
    drive(sim3, 1, Vec2(edge, edge), 10, ordinal=1)
    after3 = character(sim3, 1).pos
    travelled3 = math.hypot(after3.x - before3.x, after3.z - before3.z)
    r.check(
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
    r.check("out-of-range component rejected", component_raised)


def scenario_clamps(r: Report) -> None:
    print("\n[movement: half-court clamps]")
    # Far right wall.
    sim = boot_to_active()
    drive(sim, 1, Vec2(1.0, 0.0), 400, ordinal=1)
    r.check(
        "T1 clamps at x = +5.55",
        near(character(sim, 1).pos.x, K.CHAR_X_LIMIT, 1e-12),
        str(character(sim, 1).pos.x),
    )

    # Own back wall.
    sim = boot_to_active()
    drive(sim, 1, Vec2(0.0, -1.0), 400, ordinal=1)
    r.check(
        "T1 clamps at z = -8.55",
        near(character(sim, 1).pos.z, K.T1_Z_MIN, 1e-12),
        str(character(sim, 1).pos.z),
    )

    # Centre line: T1 may not cross into positive z.
    sim = boot_to_active()
    drive(sim, 1, Vec2(0.0, 1.0), 400, ordinal=1)
    r.check(
        "T1 cannot cross centre, stops at z = -0.45",
        near(character(sim, 1).pos.z, K.T1_Z_MAX, 1e-12),
        str(character(sim, 1).pos.z),
    )

    # Team 2's mirror limits.
    sim = boot_to_active()
    drive(sim, 2, Vec2(0.0, -1.0), 400, ordinal=1)
    r.check(
        "T2 cannot cross centre, stops at z = +0.45",
        near(character(sim, 2).pos.z, K.T2_Z_MIN, 1e-12),
        str(character(sim, 2).pos.z),
    )
    sim = boot_to_active()
    drive(sim, 2, Vec2(-1.0, 0.0), 400, ordinal=1)
    r.check(
        "T2 clamps at x = -5.55",
        near(character(sim, 2).pos.x, -K.CHAR_X_LIMIT, 1e-12),
        str(character(sim, 2).pos.x),
    )


def scenario_stale_stop(r: Report) -> None:
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
    r.check(
        "input is still fresh at exactly 250 ms",
        fresh > moved_once,
        f"{fresh} vs {moved_once}",
    )

    # One millisecond past the timeout: movement stops.
    sim.step(1251)
    stopped = character(sim, 1).pos.z
    sim.step(1400)
    still = character(sim, 1).pos.z
    r.check("stale input stops movement past 250 ms", near(stopped, still, 1e-12))


def scenario_rejections(r: Report) -> None:
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
            r.check(name, exc.code == code, f"got {exc.code}, wanted {code}")
        else:
            r.check(name, False, f"no raise, wanted {code}")

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
    r.check("reconnect seq=1 accepted on a newer ordinal", True)

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


def scenario_determinism(r: Report) -> None:
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
    r.check("two runs produce an identical final snapshot", a == b)

    c = run()
    r.check("a third run still matches", a == c)


def scenario_lifecycle_m1(r: Report) -> None:
    print("\n[lifecycle available in M1: start gate, countdown, reset]")
    sim = Simulation(FOUR)

    try:
        sim.control("start")
        r.check("start without readiness is refused", False, "no raise")
    except SimulationError as exc:
        r.check(
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
        r.check("start with three ready phones is refused", False, "no raise")
    except SimulationError as exc:
        r.check(
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
        r.check("start without a screen is refused", False, "no raise")
    except SimulationError as exc:
        r.check(
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
    r.check("start enters countdown", s.phase == "countdown", s.phase)
    r.check("countdown shows 3000 ms", s.phase_remaining_ms == 3000, str(s.phase_remaining_ms))
    r.check("round becomes 1", s.round == 1)
    r.check("epoch incremented on transition", s.epoch == 1, str(s.epoch))
    events = sim.drain_events()
    r.check("start emitted PhaseChanged", len(events) == 1, str(events))
    r.check("drain is exactly once", sim.drain_events() == [])

    entry_tick = s.tick
    for i in range(K.COUNTDOWN_TICKS - 1):
        sim.step(i)
    r.check("still counting down one tick early", sim.snapshot().phase == "countdown")
    sim.step(K.COUNTDOWN_TICKS)
    s2 = sim.snapshot()
    r.check("countdown ends after exactly 180 ticks", s2.phase == "active", s2.phase)
    r.check(
        "tick advanced 180 during countdown",
        s2.tick == entry_tick + K.COUNTDOWN_TICKS,
        f"{s2.tick} vs {entry_tick + K.COUNTDOWN_TICKS}",
    )
    r.check("active has null phase_remaining_ms", s2.phase_remaining_ms is None)
    r.check("active round clock starts at 60000", s2.remaining_ms == 60000)

    # Reset from a live phase returns to lobby, bumps epoch, keeps assignments.
    before_epoch = s2.epoch
    sim.control("reset")
    s3 = sim.snapshot()
    r.check("reset returns to lobby", s3.phase == "lobby", s3.phase)
    r.check("reset increments epoch", s3.epoch > before_epoch)
    r.check("reset retains assignments", s3.assignments == FOUR)
    r.check("reset clears round", s3.round == 0)
    r.check("reset restores spawns", (s3.characters[0].pos.x, s3.characters[0].pos.z) == K.T1_SPAWN)

    # A reset while already in lobby still bumps epoch and emits PhaseChanged.
    sim.drain_events()
    lobby_epoch = sim.snapshot().epoch
    sim.control("reset")
    r.check("lobby reset still increments epoch", sim.snapshot().epoch > lobby_epoch)
    r.check("lobby reset still emits PhaseChanged", len(sim.drain_events()) == 1)

    # tick never resets, in any phase.
    t_before = sim.snapshot().tick
    sim.step(0)
    r.check("tick advances in lobby too", sim.snapshot().tick == t_before + 1)


def scenario_immutability(r: Report) -> None:
    print("\n[immutability: networking cannot mutate simulation]")
    sim = boot_to_active()
    s = sim.snapshot()
    try:
        s.characters[0].pos.x = 99.0  # type: ignore[misc]
        r.check("snapshot vectors are frozen", False, "mutation succeeded")
    except Exception:
        r.check("snapshot vectors are frozen", True)
    r.check("characters is a tuple", isinstance(s.characters, tuple))
    r.check("balls is a tuple", isinstance(s.balls, tuple))
    r.check("assignments is a tuple", isinstance(s.assignments, tuple))

    drive(sim, 1, Vec2(0.0, 1.0), 5, ordinal=1)
    r.check(
        "an older snapshot is unaffected by later steps",
        s.characters[0].pos.z == K.T1_SPAWN[1],
    )


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

    report = Report()
    scenario_reset_snapshot(report)
    scenario_four_directions(report)
    scenario_diagonal_speed(report)
    scenario_clamps(report)
    scenario_stale_stop(report)
    scenario_rejections(report)
    scenario_determinism(report)
    scenario_lifecycle_m1(report)
    scenario_immutability(report)

    total = report.passed + len(report.failed)
    print(f"\n{report.passed}/{total} checks passed")
    if report.failed:
        print("failed:")
        for name in report.failed:
            print(f"  - {name}")
        return 1
    print("\nNot yet implemented (M3-M6): acquisition, throw, flight, swept")
    print("collision, hit scoring, round timeout, round_end/role_switch/")
    print("match_end, role swapping, readiness abort guard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
