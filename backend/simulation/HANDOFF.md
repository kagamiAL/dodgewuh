# Simulation handoff — Richard

**Freeze commit:** `0a49de1` ("Init plans."), the only commit touching 02/03/04 and HEAD at the time of
writing. All constants come from [02](../../plans/02-game-specification.md); all wire field names come from
[03](../../plans/03-api-contracts.md).

**Milestone:** M1 (roadmap H0–1 h). Scope is DTOs, Simulation signatures, reset state, deterministic movement
and the first fixtures. What is *not* implemented yet is listed at the bottom — please read that section
before assuming a behaviour exists.

**Owned paths:** `backend/simulation/**` only. I have created no file outside it.

---

## Run it

```sh
PYTHONPATH=backend python -m simulation.synthetic
PYTHONPATH=backend python -m simulation.synthetic --fixtures backend/simulation/fixtures
```

The runner currently reports **76/76 checks passed**. There is no pytest suite: this project's simulation
verification is the synthetic runner, by direction of the repo owner.

No framework import appears anywhere in this package — verified mechanically:

```sh
PYTHONPATH=backend python -c "
import sys, simulation.engine, simulation.synthetic
banned = ('fastapi','pydantic','websockets','starlette','boto3','asyncio','uvicorn')
print([m for m in sys.modules if m.split('.')[0] in banned] or 'NONE')"
```

Python 3.12, standard library only (`dataclasses`, `math`, `typing`, `json`, `argparse`, `os`, `sys`).

---

## To Alan — the seam

Import surface:

```python
from simulation import Simulation, Assignment, LegsCommand, ArmsCommand, Vec2, SimulationError
from simulation import PhaseChanged, RolesChanged, InputRejected, StateDTO
```

### Constructor and method examples

```python
sim = Simulation((
    Assignment(member_id="p1", team=1, role="arms"),
    Assignment(member_id="p2", team=1, role="legs"),
    Assignment(member_id="p3", team=2, role="arms"),
    Assignment(member_id="p4", team=2, role="legs"),
))

sim.set_assignments(assignments)          # lobby only
sim.set_readiness(
    ready_member_ids=frozenset({"p1","p2","p3","p4"}),
    connected_member_ids=frozenset({"p1","p2","p3","p4"}),
    screen_count=1,
    host_connected=True,
)
sim.control("start")                       # also "reset" | "rematch" | "abort"
sim.apply_input("p2", LegsCommand(seq=1, epoch=1, move=Vec2(0.6, 0.8)),
                received_ms=12345, ordinal=1)
sim.step(now_ms=12345)                     # exactly one fixed step
state  = sim.snapshot()                    # StateDTO, immutable
events = sim.drain_events()                # ordered, exactly once
```

All eight methods carry their **final production signatures**. M3–M6 add behaviour behind them and will not
change a signature, so you can integrate once.

### DTO ↔ wire mapping

Field names are identical in both directions; the only conversions you need are container and type shaped:

| Wire (03) | DTO (`types.py`) | Note |
|---|---|---|
| `State` | `StateDTO` | arrays → tuples |
| `Character` | `CharacterDTO` | — |
| `Ball` | `BallDTO` | — |
| `Result` | `ResultDTO` | — |
| `Assignment` | `Assignment` | — |
| `{t1,t2}` | `Score` | — |
| `Vec2 {x,z}` | `Vec2` | frozen |
| `Legs` payload | `LegsCommand` | `seq`, `epoch`, `move` — no identity fields |
| `Arms` payload | `ArmsCommand` | `seq`, `epoch`, `aim`, `action`, `strength` |

Commands carry no player or team identity by design: derive those from the authenticated member and pass the
`member_id` to `apply_input`. The simulation re-verifies role and epoch itself.

`dataclasses.asdict()` plus tuple→list gives you a dict that validates against your Pydantic `State`. The two
committed fixtures were produced exactly that way and their field sets were checked against 03 field-by-field.

### Event ordering and the drain rule

`drain_events()` returns events in generation order and clears the buffer — drain **exactly once** after each
mutation (`control`, `set_assignments`, `set_readiness`, `step`) and before the next one.

Event classes to dispatch on:

- `PhaseChanged(state: StateDTO)` → `phase.changed`
- `RolesChanged(assignments, assignment_version, epoch)` → `roles.changed`
- `InputRejected(member_id, code, message, ref_seq)` → targeted `error`

M1 emits `PhaseChanged` on every phase transition (including a lobby reset) and `RolesChanged` when
`set_assignments` changes the mapping. `InputRejected` is not emitted yet: its only producer is the
`NO_THROW_ZONE` safe-cancel path, which lands in M3.

### Error codes — synchronous vs deferred

Synchronous rejections **raise** `SimulationError(code, message)` from `apply_input` / `control` /
`set_assignments`. A single rejection is never both a raise and an event.

| Code | Raised when |
|---|---|
| `UNAUTHORIZED` | empty or non-string `member_id` |
| `WRONG_ROLE` | member holds no assignment, or command type ≠ assigned role |
| `STALE_EPOCH` | `command.epoch != state.epoch` |
| `OLD_SEQ` | `ordinal <= last accepted ordinal` (room-wide) |
| `INVALID_PHASE` | gameplay input outside `active`; `set_assignments` outside lobby; `rematch` outside `match_end` |
| `NOT_READY` | `start` without four connected ready phones and ≥1 screen |
| `INVALID_INPUT` | non-finite vector, move component outside `[-1,1]`, move magnitude > 1.001, aim length outside `[0.99,1.01]`, aim outside the team hemisphere, `strength` missing on release or present elsewhere, bad `ordinal`/`received_ms`/`seq` |

`NO_THROW_ZONE` is the **only** deferred rejection (M3), arriving as `InputRejected` with `ref_seq` set to the
offending command's `seq`.

### Duplicate defense

The simulation uses a **room-wide receive ordinal**, not a member seq counter. You own socket `seq`
validation; just pass a monotonically increasing per-room `ordinal`. A reconnected phone starting at `seq=1`
is therefore accepted, which the runner checks explicitly.

### Readiness and timing semantics

`set_readiness` **records facts and decides nothing.** Every readiness, abort and `role_switch → countdown`
decision is taken on the next `step()`. That single decision point is deliberate: it is what prevents the
duplicate-abort failure recorded at [10-planning-audit.md:16](../../plans/10-planning-audit.md).

`step(now_ms)` uses `now_ms` **only** for the 250 ms stale-input check. The active clock is tick-based.
`tick` advances once per step in every phase and never resets. Timed phase milliseconds use
`ceil(remaining_ticks * 1000 / 60)`.

---

## To Ryan (via Alan) — fixtures

Committed under `backend/simulation/fixtures/`, wrapped in the `state.snapshot` envelope from 03 so they drop
straight into a `SnapshotSource`:

| File | Shows |
|---|---|
| `reset-lobby.json` | lobby baseline: two characters at spawns, four balls at the specified middle positions, round 0, score 0, `remaining_ms` 60000, `phase_remaining_ms` null |
| `active-movement.json` | mid-round active state after real movement, so a primitive character can be mounted immediately |

Both have been checked field-by-field against the `State` definition at
[03:52](../../plans/03-api-contracts.md): envelope keys, state keys, and the key sets of `score`, every
character, every ball, every assignment and every `Vec2`. Exactly two characters sorted by team and four balls
sorted by ID.

Please commit them under `contracts/fixtures/valid/` — I do not write into `contracts/`. The remaining
fixtures Ryan needs (held, flying, result/hit, role-switch, winner) require mechanics that land in M3–M6.

---

## Documented decisions on under-specified rules

1. **Court exit is the ball *centre* leaving `[-6,6] × [-9,9]`.** 02 says court exit triggers respawn but
   specifies no radius inset. Recorded in `geometry.in_court` rather than silently chosen. Flag it if you
   disagree — it is a one-line change, but it is a rules change and so goes through me per 04.
2. **`assignment_version` starts at 1 when the constructor is given a non-empty mapping**, and 0 for an empty
   one. 03 specifies 0 for the empty case and its example 4 shows an initial four-member mapping at version 1.
3. **`remaining_ms` is derived from elapsed active ticks in every phase**, so it reads 60000 in lobby and
   countdown, counts down during active, and retains the ended round's value through `round_end` /
   `role_switch` / `match_end` — matching the 57000 in example 13.

---

## Not implemented yet — do not assume these work

M1 is a stub milestone. The following are specified, planned and **absent**:

- **M3** — ball acquisition, Hold ownership and tie-breaking, throw/release, the `NO_THROW_ZONE` safe-cancel,
  cancel-drop, flight, wall/expiry respawn. Arms `press`/`release`/`cancel` currently latch Hold and update
  aim only; **no ball moves**.
- **M4** — the swept-circle collision solver, earliest-hit resolution, simultaneous-draw detection, scoring.
- **M5** — round timeout at 3600 active ticks, `round_end`, `role_switch`, `match_end`, role swapping,
  readiness gating of the next round, first-to-three.
- **M6** — the readiness/required-device abort guard inside `step()`, and the full synthetic match.

Working now: lobby/reset state, full snapshot projection, `apply_input` validation and ordinal defense,
fixed-step movement with half-court clamps and stale stop, `countdown → active`, `reset`/`abort` to lobby,
and `start` gating on readiness and screen count.

**Not claimed:** no device test, no deployment, no integration through a real adapter or renderer. Neither
`backend/app/` nor `frontend/` exists in this repository yet, so the H4/H6/H8/H12 integration gates have not
been attempted, let alone met.
