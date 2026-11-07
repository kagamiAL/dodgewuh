# Coding-agent brief — Richard

## Identity and context

You support **Richard**, Authoritative Gameplay Simulation. Implement your assigned part of a working hackathon MVP, not a generalized platform. Four phones control two characters: Arms and Legs cooperate; teammates swap roles after every round. Python on AWS is the sole gameplay authority, Vue/PlayCanvas renders it, FastAPI routes normalized commands. The budget is approximately 24 hours. Primitive visuals and simple reliable physical control are enough.

Read in this exact order: [01 architecture](../01-architecture.md), [02 gameplay](../02-game-specification.md), [03 contracts](../03-api-contracts.md), [04 ownership](../04-repository-structure.md), [05 milestones](../05-development-roadmap.md), [your workstream plan](../teams/simulation-richard.md), then this brief. Use [06 acceptance](../06-integration-and-testing.md) during implementation. Contracts are frozen before independent coding; implementation source does not exist merely because these plans mention paths.

## Exact scope

Implement the entire authoritative gameplay simulation as pure Python. Deliver deterministic movement, ball acquisition/ownership/flight/collisions, no-throw zones, hit scoring, round timer, match/role state machines, immutable snapshots and focused tests.

## Files you own

backend/simulation/** and backend/tests/simulation/**. Own types.py, constants.py, geometry.py, engine.py and synthetic.py within that boundary.

Shared 02/03 are authoritative references; do not independently redesign them or other owners' files. Request coordinated changes through Alan (wire), Richard (rules) and Ryan (integration).

## Explicit exclusions

No FastAPI, Pydantic, WebSocket, AWS or PlayCanvas imports in simulation. Do not modify networking, frontend files or deployment. Do not implement resume, host migration or sophisticated rigid-body physics.

## Dependencies and interfaces

Python standard library; pytest supplied by Alan. Consume validated pure command DTOs converted by Alan. Implement Simulation and all methods exactly as specified in 03, and StateDTO with the same wire fields. Alan owns network schemas; ask him to commit contributed fixture JSON.

All wire message definitions come only from 03. Gameplay constants come only from 02. Mocks must use those same types and entry points; no temporary API to replace later. If a neighboring module is not yet implemented, use its specified interface with a local test double inside your owned test path and hand the integration expectation to its owner.

## Ordered implementation tasks

1. Read 01→02→03→04 and the Authoritative Gameplay Simulation plan; confirm freeze commit and exclusive ownership. Write the minimal DTOs and Simulation method signatures first.
2. Implement reset/lobby state with characters and four balls, and supply a complete snapshot fixture. Make synthetic.py run without importing FastAPI.
3. Implement fixed-step movement, normalized-vector constraints, half-court clamps, receive-ordinal/epoch defense (socket seq validation belongs to Alan) and stale-input stop. Test bounds and diagonal speed.
4. Pair with Alan to route one real Legs command through apply_input/step/snapshot. Pair with Ryan to show movement. This is the H4 priority.
5. Implement Hold acquisition, tie-breaking, single ownership, safe drop/cancel and zone release rejection. Add direct tests at exact boundaries.
6. Implement constant-speed flight, relative-motion swept circles, wall/expiry respawn and deterministic earliest hit resolution. No bounce or height physics.
7. Implement countdown/active/round_end/role_switch/match_end; score once, timeout draws, winning-round swap and first-to-three. Gate next round on all readiness.
8. Implement reset/rematch and disconnect abort-to-lobby with epoch invalidation. Clear controls and scores as specified; no reconnect resume.
9. Export immutable transition events and full snapshots; verify adapter conversion and fixtures. Run full synthetic match, then help test four actual phones.

## Testing instructions

Run `PYTHONPATH=backend pytest backend/tests/simulation` and `PYTHONPATH=backend python -m simulation.synthetic` from repo root. Include collision tunnelling, timeout edge, ownership conflict, no-throw inclusive boundary, zero/cancel/drop, duplicate scoring, role swap after draw/win, old epoch, reset and full match. A recorded command list on assigned ticks must reproduce identical final state.

Record real results and failures. Do not claim mocked behavior establishes real-device compatibility. Focus on risks and acceptance outcomes; avoid exhaustive scaffolding tests that merely repeat implementation.

## Acceptance criteria

A real Legs phone moves the correct server character; Arms acquires/throws only legally; every hit/timeout/score/swap is decided here; a four-phone match reaches a winner and rematch. Each getter/event returns immutable or defensive data so networking cannot mutate simulation.

## Definition of done and integration

Your owned code compiles/runs, focused tests pass, final production interfaces are used, and your subsystem works through the real integration path at the relevant H4/H6/H8/H12 gate. No undocumented contract drift, overlapping edits or optional work delaying a required feature. Participate in two-hour merge windows; submit small runnable changes. H18 freezes features; then fix failed acceptance cases only. A partial subsystem is not a completed MVP; report exactly what remains for cross-team integration.

## Required handoff

To Alan: constructor/method examples, DTO mapping, event ordering, error codes, exact test commands and fixture snapshots. To Ryan: reset/active/held/flying/result/role-switch/winner fixtures via Alan. Report remaining mechanics or edge cases honestly; include commit SHA and tests run.

## Final instructions to your coding agent

Follow locked architecture and technologies. Do not silently change API contracts or modify another owner's files without coordination. Do not add unrelated infrastructure. Prefer the smallest functioning implementation. Run relevant checks and actual integration where available. Report blockers/assumptions early, preserving useful independent work. Finish with a concise summary of changed files, tests and observations, remaining integration tasks and known limitations. Do not claim deployment or device testing you did not perform.
