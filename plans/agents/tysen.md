# Coding-agent brief — Tysen

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

## Identity and context

You support **Tysen**, Motion Team. Implement your assigned part of a working hackathon MVP, not a generalized platform. Four phones control two characters: Arms and Legs cooperate; teammates swap roles after every round. Python on AWS is the sole gameplay authority, Vue/PlayCanvas renders it, FastAPI routes normalized commands. The budget is approximately 24 hours. Primitive visuals and simple reliable physical control are enough.

Read in this exact order: [01 architecture](../01-architecture.md), [02 gameplay](../02-game-specification.md), [03 contracts](../03-api-contracts.md), [04 ownership](../04-repository-structure.md), [05 milestones](../05-development-roadmap.md), [your team plan](../teams/motion-morteza-tysen.md), then this brief. Use [06 acceptance](../06-integration-and-testing.md) during implementation. Contracts are frozen before independent coding; implementation source does not exist merely because these plans mention paths.

## Exact scope

Implement shared browser sensor permissions/capture, isolated sensor playground, calibrated physical Legs movement, normalized commands and real-device compatibility evidence. Choose reliable torso lean first; no step/pocket tracking research.

## Files you own

frontend/src/controllers/legs/**, frontend/src/sensors/**, frontend/src/playground/**, and docs/device-tests/**. Request route/dependency changes from Ryan.

Shared 02/03 are authoritative references; do not independently redesign them or other owners' files. Request coordinated changes through Alan (wire), Richard (rules) and Ryan (integration).

## Explicit exclusions

Do not modify Arms internals, PhoneShell or network schemas. Do not use sensor integration to estimate position. No joystick primary input, native app, gesture ML, step classifier or universal compatibility claim.

## Dependencies and interfaces

Vue/TypeScript, browser DeviceMotion/DeviceOrientation APIs, Alan Transport/generated validators, Ryan PhoneShell and route wiring. Implement SensorService/SensorSample exactly as 03; provide Morteza a stable stub immediately.

Implement calibrated(boolean) and availability(Permission) emits and per-stream freshness exactly as 03; PhoneShell owns ready messages. All wire message definitions come only from 03. Gameplay constants come only from 02. Mocks must use those same types and entry points; no temporary API to replace later. If a neighboring module is not yet implemented, use its specified interface with a local development stub within your owned source path and hand the integration expectation to its owner.

## Ordered implementation tasks

1. Read frozen documents and Motion Team plan. In first hour open actual iPhone on HTTPS, call feature-detected permission APIs from tap and display finite sample fields/age.
2. Implement one shared SensorService with subscriptions/cleanup, null-safe values and permission state. Block landscape and require recalibration rather than solving every phone orientation.
3. Build /sensors playground with raw/processed displays and recording Transport; same role interfaces as production. Coordinate route registration with Ryan.
4. Implement one-second neutral calibration, time-based smoothing, dead zone and normalized lean vector. Validate signs for forward/back/right/left on actual phone.
5. Map team-relative direction to world, send input.legs at 20 Hz plus immediate neutral zero using central seq/current epoch. Zero and clear readiness on stale data/background/rotation.
6. At H4 pair with Alan/Richard/Ryan for real phone → FastAPI → simulation → rendered movement. Use synthetic remaining slots only for this early test.
7. If continuous lean fails H3 criteria, use dominant-axis sectors/hysteresis from Motion Team plan. Do not spend time building pocket or step mode.
8. Help Morteza validate sensor fields and test all four demo devices in both roles. Verify switch/reconnect requires calibration and stale movement cannot persist.
9. Publish compatibility/test report, finish four-phone cloud match and help rehearse physically clear instructions.

## Manual verification instructions

Run `cd frontend` then manual runtime checks and `npm run typecheck`. Test neutral/noise, dead zone, diagonal cap, world-team mapping, permission denied/null sample, cleanup and stale zero. Actual iPhone by H1; target ≥9/10 correct moves per direction and stable neutral; list device/OS/browser/origin and observed sample rate.

Record real results and failures. Do not claim mocked behavior establishes real-device compatibility. Focus on risks and acceptance outcomes; avoid exhaustive scaffolding tests that merely repeat implementation.

## Acceptance criteria

Physical torso movement intentionally controls both court axes and returns to zero at neutral. Secure-context permission flow is usable; denied or stale data cannot become Ready. Same service supports Arms and both roles after swaps on four real phones.

## Definition of done and integration

Your owned code compiles/runs, manual acceptance checks pass, final production interfaces are used, and your subsystem works through the real integration path at the relevant H4/H6/H8/H12 gate. No undocumented contract drift, overlapping edits or optional work delaying a required feature. Participate in two-hour merge windows; submit small runnable changes. H18 freezes features; then fix failed acceptance cases only. A partial subsystem is not a completed MVP; report exactly what remains for cross-team integration.

## Required handoff

To Morteza: SensorService export, sample units, available fields, permission behavior and device caveats. To Ryan: component export, calibration state and route import. To Alan/Richard: normalized vectors and latency observations. Publish exact tested devices and failures, not inferred support.

## Final instructions to your coding agent

Follow locked architecture and technologies. Do not silently change API contracts or modify another owner's files without coordination. Do not add unrelated infrastructure. Prefer the smallest functioning implementation. Run relevant checks and actual integration where available. Report blockers/assumptions early, preserving useful independent work. Finish with a concise summary of changed files, manual checks and observations, remaining integration tasks and known limitations. Do not claim deployment or device testing you did not perform.
