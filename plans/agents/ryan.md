# Coding-agent brief — Ryan

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

## Identity and context

You support **Ryan**, Vue/PlayCanvas Frontend; final integration coordinator. Implement your assigned part of a working hackathon MVP, not a generalized platform. Four phones control two characters: Arms and Legs cooperate; teammates swap roles after every round. Python on AWS is the sole gameplay authority, Vue/PlayCanvas renders it, FastAPI routes normalized commands. The budget is approximately 24 hours. Primitive visuals and simple reliable physical control are enough.

Read in this exact order: [01 architecture](../01-architecture.md), [02 gameplay](../02-game-specification.md), [03 contracts](../03-api-contracts.md), [04 ownership](../04-repository-structure.md), [05 milestones](../05-development-roadmap.md), [your workstream plan](../teams/playcanvas-ryan.md), then this brief. Use [06 acceptance](../06-integration-and-testing.md) during implementation. Contracts are frozen before independent coding; implementation source does not exist merely because these plans mention paths.

## Exact scope

Implement Vue 3/Vite app, code-first PlayCanvas screen, authoritative snapshot rendering, simple interpolation, lobby/score/timer/phase UI, session store and shared PhoneShell. Coordinate small working merges and end-to-end evidence.

## Files you own

Frontend files except Alan net/generated/net tests, Morteza arms/arms tests, and Tysen legs/sensors/playground/their tests. Own frontend package.json/package-lock.json, App.vue/router, stores/session.ts, views, game/**, game tests, and docs/demo/**. Use exact ownership exclusions in 04.

Shared 02/03 are authoritative references; do not independently redesign them or other owners' files. Request coordinated changes through Alan (wire), Richard (rules) and Ryan (integration).

## Explicit exclusions

Do not implement gameplay authority or modify Richard simulation. No rigid-body physics, client score/hit/position messages, bespoke art pipeline, audio or elaborate effects. Do not edit controller internals, shared sensor source or transport schemas.

## Dependencies and interfaces

Vue 3, TypeScript, Vite, PlayCanvas Engine, Vue Router. Coordinate package additions from other frontend owners. Consume Alan Transport/ServerMessage/validators and Richard State via wire. Mount Arms/Legs with the exact 03 props and calibrated/availability events, including automatic readiness revocation and transport status.

All wire message definitions come only from 03. Gameplay constants come only from 02. Mocks must use those same types and entry points; no temporary API to replace later. If a neighboring module is not yet implemented, use its specified interface with a local development stub within your owned source path and hand the integration expectation to its owner.

## Ordered implementation tasks

1. Read frozen documents and Vue/PlayCanvas Frontend plan. Bootstrap frontend, lock dependencies, define typecheck/test/build scripts; expose placeholder routes and PhoneShell interfaces.
2. Mount PlayCanvas Application in Vue canvas with primitive arena, two characters and four balls from a validated State fixture. Clean up on unmount.
3. Build mockSource that emits full ServerMessage fixtures through the final message handler. Add reset and stale-stream cases; do not simulate gameplay in renderer.
4. Implement session store, room create/join UI, screen/phone choice and registration/token persistence through Alan transport. Show assignments/readiness in lobby.
5. At H4 integration replace mock source with live transport; render real phone → server movement. Add 100 ms interpolation only within same epoch and stale overlay; latest snapshot rendering is acceptable first.
6. Add score/remaining time/phase overlays, aim arrow, possession and no-throw visual cues. Never infer hits or send results.
7. Wire PhoneShell role components, permission/Ready controls and calibration state; on roles.changed unmount old component, reset readiness and mount new role.
8. Add host start/reset/rematch controls, winner display and clear disconnected/room-ended states. Join second screen and compare same-tick state.
9. Run four-phone deployed full match and coordinate H12 gate, H18 freeze, recording and demo. Keep main runnable and cut polish before delaying essentials.

## Manual verification instructions

Run `cd frontend && npm run typecheck`, manual runtime checks, and `npm run build` (separate commands if needed). Test interpolation boundary resets, stale freeze, mount/unmount cleanup and role-component replacement. Run acceptance rows for UI/multi-screen in 06; record real-device evidence rather than claiming a mocked test proves sensors.

Record real results and failures. Do not claim mocked behavior establishes real-device compatibility. Focus on risks and acceptance outcomes; avoid exhaustive scaffolding tests that merely repeat implementation.

## Acceptance criteria

Screen displays a playable primitive arena from server state; two screens agree on score/phase; late join works; four phones show correct role before and after switch; host can start a full match and rematch. No client authoritative decisions exist.

## Definition of done and integration

Your owned code compiles/runs, manual acceptance checks pass, final production interfaces are used, and your subsystem works through the real integration path at the relevant H4/H6/H8/H12 gate. No undocumented contract drift, overlapping edits or optional work delaying a required feature. Participate in two-hour merge windows; submit small runnable changes. H18 freezes features; then fix failed acceptance cases only. A partial subsystem is not a completed MVP; report exactly what remains for cross-team integration.

## Required handoff

To motion owners: component imports, route path, props/emits and PhoneShell readiness lifecycle. To Alan: accepted Transport messages and observed network failures without secrets. To Richard: rendering fixture gaps. To all: integration commit, passing gates, unresolved defects, demo recording and known-good release SHA.

## Final instructions to your coding agent

Follow locked architecture and technologies. Do not silently change API contracts or modify another owner's files without coordination. Do not add unrelated infrastructure. Prefer the smallest functioning implementation. Run relevant checks and actual integration where available. Report blockers/assumptions early, preserving useful independent work. Finish with a concise summary of changed files, manual checks and observations, remaining integration tasks and known limitations. Do not claim deployment or device testing you did not perform.
