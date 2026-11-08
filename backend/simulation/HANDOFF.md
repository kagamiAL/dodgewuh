# Simulation handoff — Richard

**Branch:** `feature/richard-physics` (the path named in
[04:82](../../plans/04-repository-structure.md) is `feat/richard-sim`; the working branch was renamed when the
physics work started — same owned paths).
**Implementation commit:** see `git log -1 --format=%H`. Content so far is M1 (`44b43fe`) plus
`31cfc6a` (project-instruction alignment) on top of the merge of `main` at `ebccfe4`, then ordered task 5
(acquisition, ownership, safe cancel, no-throw zone), task 6 (flight, respawn, swept collision, earliest-hit
resolution) and task 7 (scoring, timeout draw, round/match lifecycle, role swapping, readiness gating).
**Manual checks performed:** build check (`compileall`, all modules), runtime diagnostics (262/262 observations
matching, including a complete four-round match with a draw, a winner and a rematch), constants audit against
the 02 table, seam-signature and DTO field-set introspection against 03, and fixture field-set validation.
All listed under "Manual verification steps" below.

**Contract commits:** frozen at `0a49de1` ("Init plans."); amended by `ebccfe4` ("Amend MD to not make
tests."), which is merged into this branch. I re-diffed 02 and 03 across that amendment: **no normative rule
or wire-schema change** — 02 and 03 received only the project-instruction banner and test→manual-check
wording. Every constant and field name in this package is therefore still correct. All constants come from
[02](../../plans/02-game-specification.md); all wire field names come from
[03](../../plans/03-api-contracts.md).

**Project instruction compliance (dodgewuh):** this package contains no test framework, no test dependency,
no test file and no test directory, and no milestone or handoff is gated on an automated test command.
`backend/tests/simulation/**` was removed from my ownership in `ebccfe4` and was never created. Verification
is a build check plus the synthetic runner, which 06 designates a manual diagnostic tool and the instruction
explicitly retains as a runtime validator.

**Progress:** ordered tasks 1–7 of [the brief](../../plans/agents/richard.md) are implemented: DTOs and seam
signatures, reset state, deterministic movement, input defense, Hold acquisition and ownership, safe
cancel/no-throw zone, and constant-speed flight with wall/expiry respawn, swept-circle collision and
earliest-hit resolution, and the complete lifecycle — exactly-once scoring, the 3600-tick timeout draw,
`lobby → countdown → active → round_end → role_switch → countdown … → match_end`, every-round role swapping,
readiness gating of the next round, and first-to-three. A synthetic match plays to a winner and rematches.
Task 8's remaining piece — the abort guard inside `step()` — is **not** implemented; read the bottom section
before assuming a behaviour exists.

**Owned paths:** `backend/simulation/**` only. I have created no file outside it.

---

## Manual verification steps

```sh
# 1. build check — stdlib only, no dependencies
PYTHONPATH=backend python -m compileall -q backend/simulation

# 2. runtime diagnostics against the rules in 02/03
PYTHONPATH=backend python -m simulation.synthetic

# 3. regenerate the fixtures handed to you
PYTHONPATH=backend python -m simulation.synthetic --fixtures backend/simulation/fixtures
```

Step 2 currently reports **262/262 observations match the specified rules**, printing each rule it observed so
the output can be read and judged by a person. A deviation prints `DEVIATION` with observed-vs-expected values
and exits non-zero.

**Python version:** your `backend/pyproject.toml` pins `>=3.12,<3.13` and `.python-version` says `3.12`. My
machine has 3.14.0 installed, so I ran the diagnostics there; I also verified all six modules parse under
`ast.parse(..., feature_version=(3,12))`. The package uses no syntax or stdlib feature newer than 3.12, but
the 3.12 run is still unobserved on my side — please confirm it under the pinned interpreter in your venv or
container when you wire it up.

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

All eight methods carry their **final production signatures**. Tasks 7–8 add behaviour behind them and will
not change a signature, so you can integrate once.

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

`PhaseChanged` is emitted on every phase transition (including a lobby reset). `RolesChanged` is emitted when
`set_assignments` changes the mapping **and** after every round's role swap. `InputRejected` is emitted for
exactly one case: the `NO_THROW_ZONE` safe cancel, carrying the offending release's `seq` in `ref_seq`.

Bundles you must forward in order (03 requires this and 06 calls out the winning-round case specifically):

| Moment | Events, in order |
|---|---|
| hit or timeout | `PhaseChanged(round_end)` |
| result display ends | `PhaseChanged(role_switch)`, `RolesChanged` |
| …on the winning round | `PhaseChanged(role_switch)`, `RolesChanged`, `PhaseChanged(match_end)` — three events from one `step()` |
| readiness satisfied in role_switch | `PhaseChanged(countdown)` |
| countdown ends | `PhaseChanged(active)` |

Epoch increases on every one of those, so a bundle never regresses epoch. The runner asserts that explicitly
for both the ordinary and the winning-round bundle. A hit is observable either as `PhaseChanged(round_end)`
or as `snapshot().result`; they are produced from the same mutation.

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

`NO_THROW_ZONE` is the **only** deferred rejection, arriving as `InputRejected` with `ref_seq` set to the
offending command's `seq`. Per [02:38](../../plans/02-game-specification.md) it is not a pure rejection: it
also drops the held ball grounded at the character centre, which is the "safe cancellation" the rules
require. Expect state to change on that error.

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
| `active-held.json` | possession: `mode:"held"`, `owner_team:1`, ball riding on the character centre, `held_ball_id` set |
| `active-flying.json` | a real release in flight: `mode:"flying"`, `shooter_team:1`, non-zero `velocity`, `owner_team` null |
| `round-end-hit.json` | a scored round: `phase:"round_end"`, `score` 1–0, `result.reason:"hit"` with winner/victim/ball, `phase_remaining_ms:2000`, arena **not** yet reset |
| `round-end-timeout.json` | a timeout draw: `result.reason:"timeout"`, `score` 0–0, no winner or victim |
| `role-switch.json` | post-swap wait state: arena reset to spawns, `assignment_version` bumped, roles traded within each team, `phase_remaining_ms` null, result still visible |
| `match-end-winner.json` | end of match: `phase:"match_end"`, `winner:1`, final `score` 3–0, deciding result retained |

All have been checked field-by-field against the `State` definition at
[03:52](../../plans/03-api-contracts.md): envelope keys, state keys, and the key sets of `score`, every
character, every ball, every assignment and every `Vec2`. Exactly two characters sorted by team and four balls
sorted by ID. Every fixture was also re-checked against the cross-field invariants — `owner_team` only when
held, `shooter_team` only when flying, `respawn_in_ms` only when respawning, zero velocity when not flying,
`phase_remaining_ms` only in countdown/round_end, `winner` only at match_end.

This is the complete set named in my brief's handoff requirement: reset, active, held, flying, result,
role-switch and winner. Please commit them under `contracts/fixtures/valid/` — I do not write into
`contracts/`.

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
4. **A respawning ball waits at its own original spawn for the whole 1 second**, rather than at the point it
   left play. 02 specifies the delay and the spawn but no intermediate position, and a respawning ball damages
   nobody, so it is parked where it will reappear. Ryan: a respawning ball therefore has a meaningful `pos`
   plus a counting-down `respawn_in_ms`, which is enough to fade it in.
5. **The ball that scores a hit stays `flying`** at the position its advance reached, matching the `round_end`
   example at [03:328](../../plans/03-api-contracts.md), which shows the hit ball still flying with velocity.
   It is not snapped to the exact impact point and not respawned in the deciding tick.
6. **A hit at or before a clipped wall/lifetime endpoint is a hit, not a respawn** — 02 states this directly,
   and the runner checks the case where both would happen in one tick.
7. **The round number increments on entering countdown**, so the first round of a match is round 1 and
   `lobby` reads round 0. A timeout or draw still advances the round number, since a round was played.
8. **The deciding tick counts toward the round clock, and the clock then stops.** The tick a hit lands in did
   elapse, so it is counted; every tick after the round is decided is not. That is what makes `remaining_ms`
   retain the ended round's value through `round_end` / `role_switch` / `match_end` per 03.
9. **The role swap happens on entering `role_switch`, before the `match_end` check**, because 02 says to swap
   after *every* round "including the winning round" and to enter match_end "after the swap". So a won match
   emits `PhaseChanged(role_switch)`, `RolesChanged`, then `PhaseChanged(match_end)` from one `step()`, and
   the final assignments a rematch retains are the post-swap ones.
10. **Gameplay edge worth a team decision: a throw launched from the sideline can be lost instantly.** 02 says
   a throw launches at `centre + aim × 0.65`, and the character `x` limit is 5.55 while the court wall is 6.0.
   A character hugging the sideline and aiming diagonally (`aim.x` up to ~0.98, since only `|aim.z| ≥ 0.2` is
   required) launches at `x ≈ 6.19`, already outside the court — so "court exit triggers respawn" fires in the
   launch tick and the ball respawns without travelling. I implemented both rules literally rather than
   inventing an unspecified clamp on the launch point. This is reachable in play but narrow, and the fix
   (clamp the launch point into the court, or inset the wall test by the ball radius) is a **rules change**, so
   it goes through the coordinated process in 04 rather than into my code unilaterally. Flagging, not fixing.

---

## Not implemented yet — do not assume these work

The following is specified, planned and **absent**:

- **Task 8 — the abort guard inside `step()`.** `control("abort")` and `control("reset")` already perform the
  full reset to lobby, and `control("rematch")` works from `match_end`. What is missing is `step()` deciding
  *on its own* from the facts in `set_readiness` that a required phone has gone unready or disconnected, or
  that every screen is gone, during a non-lobby phase — and aborting for it. **Until that lands, the adapter
  must call `control("abort")` itself** when it observes a required-device loss or a current-epoch
  `ready=false` during countdown/active. The simulation will not infer it. 03 reserves that single decision
  point for `step()` precisely so there is no duplicate abort, so this is the last gap, not a design change.

Working now: lobby/reset state, full snapshot projection, `apply_input` validation and ordinal defense,
fixed-step movement with half-court clamps and stale stop, Hold acquisition with
nearest/tie-break/single-ownership, safe cancel and `NO_THROW_ZONE`, release and launch, constant-speed
flight, wall and lifetime respawn, swept-circle collision against the opponent only, earliest-hit resolution
including the simultaneous draw, exactly-once scoring, the 3600-tick timeout draw, the full phase machine
through `match_end`, every-round role swapping with `RolesChanged`, readiness gating of the next round,
first-to-three, and `reset`/`abort`/`rematch` to lobby.

**Not claimed:** no device check, no deployment, no integration through a real adapter or renderer. The
H4/H6/H8/H12 integration gates have not been attempted, let alone met.

## Wiring into your bootstrap

I read `origin/backend-alan` at `0329530`. `backend/app/worker.py` says "Richard's simulation will run in this
process" — that is the right home. From `backend/`, `from simulation import Simulation` resolves with no
`PYTHONPATH` gymnastics, since `simulation/` sits beside `app/`. Nothing in this package needs to be added to
`pyproject.toml`: it imports only the standard library, so it has no dependency footprint and no build step.

Two things I noticed while reading your branch, both yours to decide and neither blocking me:

1. Your `compose.yaml` splits a coordinator from a game worker, while
   [01:3](../../plans/01-architecture.md) describes one FastAPI process holding one simulation object per
   room. A split is fine for the simulation — it is a plain synchronous object with no shared state between
   instances — but 01 also requires that **one room's mutations are serialized on a single event loop**. If a
   room could ever be served by two worker replicas, that invariant breaks and so does authority. Worth
   pinning a room to exactly one worker.
2. `.gitignore` on your branch covers `__pycache__/`, which main does not yet have. I had committed six
   `.pyc` files into my own path; I have untracked them in this branch.
