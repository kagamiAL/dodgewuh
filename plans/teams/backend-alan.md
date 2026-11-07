# Backend / Networking / Infrastructure — Alan

Connect the working game with the smallest backend. Richard supplies all gameplay mechanics. Your adapter converts validated input and pure snapshots without editing simulation internals. Read [03](../03-api-contracts.md) as authoritative wire/interface specification and [08](../08-deployment-runbook.md) as deployment specification.

## Necessary scope

Create FastAPI app, REST room registration, unique code generation, session tokens, exactly four phone slots, up to four screens, immutable host identity, native WebSocket authentication/Origin checks, readiness/status, host command authorization, serialized input routing, one Simulation per room, full state broadcasting, safe disconnect-to-lobby reset, room cleanup and health/logging. Deploy one instance with Caddy/GoDaddy/EIP and Terraform. Do not implement collision, movement, scoring, timer or role-switch rules. Assign initial slots; thereafter mirror simulation assignments.

Optional work excluded until acceptance passes: QR image generation, accounts, persistent room recovery, reconnection resume, distributed coordination, autoscaling, metrics service, fancy dashboards or complex CI/CD. Room code copy and reconnect-to-lobby are enough. A few small modules and one deployment script suffice.

## Modules and sequence

1. protocol.py implements [03] models and envelope registry. Export matching TS types/validators in owned generated directory, good/bad JSON fixtures and contract tests. Confirm DTO mapping with Richard and Transport interface with Ryan/Tysen/Morteza.
2. rooms.py stores room ID/code, members, token hashes or securely compared opaque tokens, revision, host, readiness, connections and Simulation reference. Allocate phone slots in fixed order, no interactive team editor. Use cryptographically random session tokens (at least 32 random bytes), six-character collision-checked codes.
3. main.py exposes exact REST endpoints and health, normalizes errors and no-store headers. Rate/cap limits are simple in-memory counters; no authentication product.
4. ws.py handles first-frame hello, one socket/member, session ping/pong, sender queue and disconnect cleanup. Every input identity derives from socket. Unauthorized screens cannot send motion; wrong-role phones cannot control another role.
5. simulation_adapter.py maps network models to Richard DTOs; runner.py schedules one fixed-step authority per room, broadcasts full snapshots and reliable events. Use Richard's synthetic script/fixtures for expected behavior. Never await socket sends in step.
6. Integrate minimal movement by H4 with real phone and Ryan screen; replace MockSimulation factory before production. This gate outranks rare edge-case polish.
7. Add ready/start/reset/rematch and role event routing; apply updated assignments/readiness atomically from simulation transitions. Disconnect clears input and returns match to lobby safely, retaining seats briefly for reconnect; host loss closes room after grace.
8. TTL cleanup removes empty/expired rooms and sender tasks. Health reports build and room count; log rejections/overruns without tokens or sensors.
9. Run Terraform/DNS/Caddy steps in parallel when network waiting allows. Public TLS/WSS target H6; full deployed match H10–12.

## Ownership, tests and assistance

Own backend/app/** and backend tests except simulation; backend dependency manifests; contracts/**; frontend/src/net/** and generated/** plus net tests; infra/**, deploy/**, .github/** and enumerated root files in [04](../04-repository-structure.md). Richard owns simulation directory even though it executes in your process. Ryan owns frontend dependency manifests; request Zod/transport script changes from him. No edits to gameplay constants to fix adapter bugs.

MockSimulation implements exact [03] methods and scriptable State. Test creation/join/auth, ready gates, invalid/duplicate/stale command, sender backpressure, room TTL, disconnect/reset and process restart behavior. Use FastAPI test clients for routes and real WebSocket clients for one integration test. Synthetic messages must validate the same schemas as phones. Ryan runs cloud UI smoke; Tysen validates physical phones; Richard pairs on conversion. Keep deployment responsibility with you, rather than giving everyone AWS credentials.

## Acceptance checklist

- [ ] Phone can create/join through UI, authenticate and move character through real simulation.
- [ ] Four slots remain unique; host-only actions enforced; late screen receives full baseline.
- [ ] No raw sensors or client-authoritative results accepted; every message validated.
- [ ] Inputs/snapshots work for four phones plus two screens without diverging rooms.
- [ ] Disconnect cannot leave motion/Hold stuck; lobby reset and reconnect are clear.
- [ ] One-worker EC2 serves frontend HTTPS and WSS; health, logs, rollback and cleanup commands are documented and exercised as appropriate.

Definition of done: backend tests/contract fixtures pass, production uses Richard Simulation, complete cloud match passes, deployment SHA and known limitations recorded. Handoff to all: base origin, exact startup commands, fixture locations, registration examples, logs for diagnostics and how room loss is displayed. Handoff to Ryan coordinator: known-good artifact, rollback target and acceptance results. Do not expose credentials/tokens in handoff.
