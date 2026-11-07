# Coding-agent brief — Alan

> **Architecture amendment:** dodgewuh uses Docker, a coordinator VM plus game worker VM(s), and PostgreSQL for durable records. [Persistence plan](../11-sql-persistence.md) supersedes earlier single-process, no-database and systemd-backend instructions. Public message schemas remain unchanged; live simulations stay in worker memory.

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

## Identity and context

You support **Alan** on **dodgewuh**, Backend / Networking / Infrastructure. Implement your assigned part of a working hackathon MVP, not a generalized platform. Four phones control two characters: Arms and Legs cooperate; teammates swap roles after every round. Python on AWS is the sole gameplay authority, Vue/PlayCanvas renders it, FastAPI routes normalized commands. The budget is approximately 24 hours. Primitive visuals and simple reliable physical control are enough.

Read in this exact order: [01 architecture](../01-architecture.md), [02 gameplay](../02-game-specification.md), [03 contracts](../03-api-contracts.md), [04 ownership](../04-repository-structure.md), [05 milestones](../05-development-roadmap.md), [your team plan](../teams/backend-alan.md), then this brief. Use [06 acceptance](../06-integration-and-testing.md) during implementation. Contracts are frozen before independent coding; implementation source does not exist merely because these plans mention paths.

## Exact scope

Implement FastAPI room/session API, native WebSocket transport, authoritative simulation adapter/runner, input validation, full-state broadcast and Docker coordinator/worker AWS deployment with PostgreSQL persistence. Keep backend small enough to integrate within hours.

## Files you own

backend/** except simulation/** and manual checks/simulation/**; contracts/**; frontend/src/net/** and generated/**; infra/**; deploy/**; .github/**; root README.md/.gitignore/.env.example/Makefile. See exact exclusions in 04.

Shared 02/03 are authoritative references; do not independently redesign them or other owners' files. Request coordinated changes through Alan (wire), Richard (rules) and Ryan (integration).

## Explicit exclusions

No gameplay mechanics or edits inside Richard simulation. No Redis, accounts, API Gateway, load balancer, host migration, reconnect resume or QR generation. No client-authoritative relay. No secrets in committed files.

## Dependencies and interfaces


All wire message definitions come only from 03. Gameplay constants come only from 02. Mocks must use those same types and entry points; no temporary API to replace later. If a neighboring module is not yet implemented, use its specified interface with a local development stub within your owned source path and hand the integration expectation to its owner.

## Ordered implementation tasks

1. Read 01→02→03→04, Backend plan and 08. Freeze schemas/fixtures; scaffold backend/root and final Transport interface. Verify AWS/GoDaddy access immediately.
2. Implement Pydantic event registry and matching strict TS validators, fixture corpus and normalized REST error envelope. Keep only required events.
3. Implement room creation/join, random codes/tokens, immutable screen host and ordered four-phone slots; register initial assignments with Richard Simulation.
4. Implement first-message hello, Origin/auth checks, per-member socket and session heartbeat. Full welcome has room and state; no query tokens.
5. Implement conversion adapter and one serialized runner per room. Route normalized Legs to Richard, send snapshots to Ryan. Pair for H4 real-phone vertical slice before polishing operational features.
6. Add Arms edges, readiness/start/reset/rematch authorization, role mapping updates, bounded queues/rate validation and immediate disconnect-to-lobby reset. Seats reserved briefly; no resume.
7. Implement simple TTL cleanup, health/build and safe logs. Test unauthorized/wrong-role/old-epoch inputs and slow sockets.
8. Provision coordinator/worker EC2 and PostgreSQL data disk with Terraform, configure Porkbun DNS and Docker/Caddy TLS/static/proxy per plan 11. Build/deploy with 08; target public WSS H6.
9. Run four-phone full-match cloud smoke and rollback rehearsal with Ryan. Record SHA, URLs/start commands and unresolved constraints; prepare cleanup.

## Manual verification instructions

Manually verify backend endpoints and real simulation integration. Verify frontend transport and fixture handling in the browser; run type checks and builds. Terraform fmt/validate/plan precede apply. Verify public health, browser HTTPS trust and WSS snapshots, then four-phone match; healthy REST alone is insufficient.

Record real results and failures. Do not claim mocked behavior establishes real-device compatibility. Focus on risks and acceptance outcomes; avoid exhaustive scaffolding tests that merely repeat implementation.

## Acceptance criteria

One authenticated role command reaches the correct pure Simulation; same full state reaches screens/phones; invalid authority attempts rejected. Four-phone role switching/full match works on EC2 over HTTPS/WSS; disconnect safely resets, cloud logs/rollback/cleanup are usable.

## Definition of done and integration

Your owned code compiles/runs, manual acceptance checks pass, final production interfaces are used, and your subsystem works through the real integration path at the relevant H4/H6/H8/H12 gate. No undocumented contract drift, overlapping edits or optional work delaying a required feature. Participate in two-hour merge windows; submit small runnable changes. H18 freezes features; then fix failed acceptance cases only. A partial subsystem is not a completed MVP; report exactly what remains for cross-team integration.

## Required handoff

To everyone: endpoint origin, registration/Transport examples, fixture paths and startup commands. To Richard: adapter conversion observations/errors. To Ryan coordinator: deployment SHA, previous release, smoke evidence and known limitations. Never include tokens, AWS secrets or private keys.

## Final instructions to your coding agent

Follow locked architecture and technologies. Do not silently change API contracts or modify another owner's files without coordination. Do not add unrelated infrastructure. Prefer the smallest functioning implementation. Run relevant checks and actual integration where available. Report blockers/assumptions early, preserving useful independent work. Finish with a concise summary of changed files, manual checks and observations, remaining integration tasks and known limitations. Do not claim deployment or device testing you did not perform.
