# Coding-agent brief — Morteza

## Identity and context

You support **Morteza**, Motion Team. Implement your assigned part of a working hackathon MVP, not a generalized platform. Four phones control two characters: Arms and Legs cooperate; teammates swap roles after every round. Python on AWS is the sole gameplay authority, Vue/PlayCanvas renders it, FastAPI routes normalized commands. The budget is approximately 24 hours. Primitive visuals and simple reliable physical control are enough.

Read in this exact order: [01 architecture](../01-architecture.md), [02 gameplay](../02-game-specification.md), [03 contracts](../03-api-contracts.md), [04 ownership](../04-repository-structure.md), [05 milestones](../05-development-roadmap.md), [your team plan](../teams/motion-morteza-tysen.md), then this brief. Use [06 acceptance](../06-integration-and-testing.md) during implementation. Contracts are frozen before independent coding; implementation source does not exist merely because these plans mention paths.

## Exact scope

Implement Arms mobile UI, large Hold button, calibrated orientation aiming, simple motion-gated release, fixed-strength initial throw, safe cancellation and normalized commands. Deliver a working phone throwing loop before strength polish.

## Files you own

frontend/src/controllers/arms/** and frontend/tests/arms/** only. Put ArmsController.vue, calibration/gesture logic and replay fixtures here. Request route/package changes from Ryan; sensor changes from Tysen.

Shared 02/03 are authoritative references; do not independently redesign them or other owners' files. Request coordinated changes through Alan (wire), Richard (rules) and Ryan (integration).

## Explicit exclusions

No physical volume-button capture, absolute velocity integration, gameplay pickup/score logic, custom WebSocket or duplicate permission service. Variable strength is outside the MVP. No touch-only release masquerading as motion.

## Dependencies and interfaces

Vue/TypeScript and Vitest from Ryan; Tysen SensorService/SensorSample; Alan Transport/generated ClientMessage; Ryan PhoneShell props/emits. Follow action/seq/epoch/aim/strength contracts in 03 and tuning plan in Motion Team document.

Implement calibrated(boolean) and availability(Permission) emits and per-stream freshness exactly as 03; PhoneShell owns ready messages. All wire message definitions come only from 03. Gameplay constants come only from 02. Mocks must use those same types and entry points; no temporary API to replace later. If a neighboring module is not yet implemented, use its specified interface with a local test double inside your owned test path and hand the integration expectation to its owner.

## Ordered implementation tasks

1. Read 01→02→03→04 and Motion Team plan. Create component with exact props/emits and fake final-interface SensorService/Transport for local tests.
2. Build large Hold control using pointer capture and one active pointer. Test press, normal release, pointercancel and lost capture ordering before motion integration.
3. Consume shared permission/sensor service; calibrate neutral orientation over one second and emit calibrated only with sufficient finite samples.
4. Convert tilt to clamped forward aim using team-world mapping. Send typed aim at 20 Hz and immediate press/cancel edges with central seq/current epoch.
5. Add recent motion peak gate and fixed strength 0.5 for release; freeze pre-swing aim. Stationary release must cancel, not throw.
6. Cancel on focus/visibility loss, role change, rotation, stale sensors and connection loss. Stop subscriptions on unmount; clear Hold before new epoch.
7. At H4–6 pair with Richard/Ryan: acquire while Legs moves into range, back outside zone, aim and throw. Display server possession/rejection rather than assuming pickup.
8. Test actual iPhone 20 deliberate throws and ten cancellation cases; tune thresholds only based on recorded observations. Verify this Arms UI mounts after role swaps on all four phones.
9. Keep fixed strength, use spare time to fix cancellation/device defects, then complete deployed full match and handoff.

## Testing instructions

Run `cd frontend` then `npm test -- --run tests/arms` and `npm run typecheck`. Replay SensorSample records for stationary release, valid recent peak, expired peak, pointercancel and stale state. On actual phones target ≥18/20 intentional gesture/releases and zero accidental cancellation throws; record what was actually measured.

Record real results and failures. Do not claim mocked behavior establishes real-device compatibility. Focus on risks and acceptance outcomes; avoid exhaustive scaffolding tests that merely repeat implementation.

## Acceptance criteria

Arms can hold/acquire with Legs cooperation, aim physically, and launch only with gesture plus normal release. Cancel and lost connection never launch; role switching requires fresh calibration/press. Fixed strength is a complete MVP outcome.

## Definition of done and integration

Your owned code compiles/runs, focused tests pass, final production interfaces are used, and your subsystem works through the real integration path at the relevant H4/H6/H8/H12 gate. No undocumented contract drift, overlapping edits or optional work delaying a required feature. Participate in two-hour merge windows; submit small runnable changes. H18 freezes features; then fix failed acceptance cases only. A partial subsystem is not a completed MVP; report exactly what remains for cross-team integration.

## Required handoff

To Tysen: required finite sensor fields, failed device samples without personal data, chosen threshold. To Ryan: component export/calibrated behavior and error UI. To Richard/Alan: valid command traces, rejection cases, tests/device results and unresolved blockers.

## Final instructions to your coding agent

Follow locked architecture and technologies. Do not silently change API contracts or modify another owner's files without coordination. Do not add unrelated infrastructure. Prefer the smallest functioning implementation. Run relevant checks and actual integration where available. Report blockers/assumptions early, preserving useful independent work. Finish with a concise summary of changed files, tests and observations, remaining integration tasks and known limitations. Do not claim deployment or device testing you did not perform.
