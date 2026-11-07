# Authoritative gameplay simulation — Richard

Deliver the pure Python simulation that decides every gameplay outcome. This is a separate workstream from Ryan's renderer and Alan's networking. Richard owns mechanics; Alan integrates the simulation without changing its internal logic.

Read [architecture](../01-architecture.md), [rules](../02-game-specification.md), [contracts](../03-api-contracts.md) and [ownership](../04-repository-structure.md) before implementation. Keep this a working MVP: implement the playable loop before polish.

## Scope and ownership

Own backend/simulation/** and backend/tests/simulation/** only. Implement constants, plain DTOs, movement clamps, ball acquisition/ownership, flat flight, swept collisions, no-throw zones, scoring, active timer, round/match/reset state machines, role swaps and immutable snapshots. No FastAPI, Pydantic, WebSocket, AWS or PlayCanvas dependencies inside simulation.

Use [02](../02-game-specification.md) as the sole rules/constants authority and implement the exact Simulation seam in [03](../03-api-contracts.md). No advanced physics, reconnect resume or host migration. Straight trajectories and fixed-strength phone commands are sufficient for the MVP.

## Implementation sequence

1. Publish pure DTOs, Simulation signatures and a reset snapshot. Supply fixtures through Alan so Ryan can render immediately.
2. Implement fixed-step movement, half-court constraints and stale-input stop using synthetic final-schema commands. Run without FastAPI.
3. Pair with Alan at H2 on input/snapshot conversion. At H4, prove a real phone changes the authoritative position shown by Ryan's renderer.
4. Add Hold acquisition, deterministic ownership, safe cancellation, zone validation and flight. Pair with Morteza for the two-phone pickup/throw gate.
5. Add swept collision, exactly-once scoring, timeout draws and round transitions. Test exact boundaries and simultaneous hits.
6. Add every-round role swapping, calibration/readiness gating, first-to-three, rematch and disconnect abort-to-lobby.
7. Complete a synthetic full match, then participate in the four-phone cloud match. Fix gameplay blockers before adding anything optional.

## Mocks and handoffs

The synthetic runner uses the same pure command DTOs and Simulation methods as Alan's adapter; no alternate control API. Alan owns network models, generated frontend types and canonical fixtures. Send him reset/active/held/flying/result/role-switch/winner snapshots, conversion examples and expected rejection cases.

Ryan consumes snapshots, not simulation internals. Coordinate state display requirements with [Ryan's plan](playcanvas-ryan.md), but do not edit his frontend. Report changes to rules through the coordinated contract process before either consumer implements them.

## Tests and acceptance

- [ ] Movement clamps, diagonal speed and stale stop pass pure tests.
- [ ] Four balls reset correctly; each has at most one owner.
- [ ] Cancel never launches; inclusive no-throw boundaries are enforced.
- [ ] Swept hits and timeout award points exactly as specified; held balls do not shield.
- [ ] Every completed round swaps roles; readiness gates the next round.
- [ ] Winner, rematch and disconnect reset work without old-epoch input leaking through.
- [ ] Real phone movement and a complete four-phone hosted match use this simulation.

Run `PYTHONPATH=backend pytest backend/tests/simulation` and the synthetic runner. Definition of done: focused tests pass, immutable snapshots/events convert through Alan's adapter, and Richard-owned acceptance rows in [06](../06-integration-and-testing.md) are observed. Handoff includes commit SHA, test results, fixtures, conversion notes and outstanding integration defects. Use [Richard's coding-agent brief](../agents/richard.md) for execution.
