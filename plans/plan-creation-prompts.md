# Hack the Change 2026 — Generate Complete Development Planning Package

You are acting as a principal software architect, multiplayer game engineer, and hackathon technical lead.

## Your task

Read the entire `master-prompt.md` file in this repository.

Treat it as the comprehensive source of project requirements, gameplay specifications, deliverables, acceptance criteria, and planning expectations.

**Your job is to execute that prompt by creating every required Markdown planning file directly in the repository.**

Do not merely outline the plans. Write the files.

However, several architectural decisions have changed since `master-prompt.md` was written. The overrides below take precedence over any conflicting instructions in that file.

## 1. Final architecture — LOCKED

We are building a 2v2 cooperative, motion-controlled dodgeball game.

Each team consists of two humans controlling one virtual character: an Arms player and a Legs player.

Our architecture is **server-authoritative**.

- The authoritative gameplay simulation runs in Python on AWS alongside the FastAPI backend.
- Each active game room has exactly one authoritative simulation.
- The server exclusively owns character positions, ball physics, collisions, ball ownership, round timers, scoring, round transitions, and match results.
- Smartphones process motion sensors locally and send normalized gameplay commands through WebSockets.
- FastAPI manages room membership, player identity, role assignment, input routing, and authoritative state broadcasting.
- PlayCanvas renders the game on desktop browsers. It does not determine authoritative game outcomes.
- Multiple screen clients render the same server-authoritative state, using interpolation where appropriate.
- Do not implement client-authoritative simulation, peer-to-peer networking, or host migration.
- Use lightweight deterministic 2D simulation mathematics to drive a visually 3D PlayCanvas arena.
- For the MVP, one FastAPI process with in-memory rooms and game simulations is sufficient.

## 2. Final developer assignments — LOCKED

These assignments supersede the original master prompt.

**Richard — Authoritative Python Gameplay Simulation**

- Character movement and court constraints
- Dodgeball acquisition, trajectories, and collisions
- No-throw zones
- Hit detection, scoring, and round timer
- Round/match state machines
- Role-switching game logic
- Simulation snapshots and unit tests
- Pure Python gameplay modules with no dependency on AWS or WebSocket connections

**Ryan — Vue + PlayCanvas Game Frontend**

- PlayCanvas integration and arena
- Characters, balls, and animations
- Rendering authoritative game-state snapshots
- Client-side interpolation
- Scoreboard, timer, and round transitions
- Screen-specific lobby and game UI
- Multi-screen rendering consistency
- Mock-state rendering harness

**Morteza — Arms Controller**

- Arms mobile UI
- Large Hold button
- Phone aiming
- Throw gesture recognition
- Throw strength estimation
- Safe cancellation
- Sensor calibration
- Normalized Arms gameplay commands

**Tysen — Legs Controller**

- Legs mobile UI
- Motion sensor capture and permissions
- Physical directional movement detection
- Calibration
- Normalized Legs gameplay commands
- Motion-based fallback controls
- Real-device compatibility testing

**Alan — Backend, Networking, Infrastructure**

- FastAPI application
- Room creation and join codes
- Player identity and assignments
- WebSocket connection management
- Input validation and routing
- Integrating Richard's simulation with FastAPI
- Authoritative snapshot broadcasting
- Disconnects and room lifecycle
- AWS EC2, Terraform, deployment, HTTPS/WSS
- Backend integration tests and operational logging

Richard and Ryan remain the two-person **Game Team**, even though Richard's simulation executes on the server.

Alan does NOT implement the gameplay simulation itself.

Design strict module boundaries so that Alan can integrate Richard's simulation without modifying its internal logic.

## 3. Hosting decisions — LOCKED

We have access to a free **GoDaddy domain**.

Use the simplest viable deployment:

- AWS EC2, single instance
- Terraform-managed infrastructure
- FastAPI backend
- Caddy reverse proxy
- HTTPS and WSS through Caddy automatic TLS
- Vue/Vite static frontend served by Caddy
- GoDaddy-managed DNS pointing to an Elastic IP
- Same-origin frontend and backend wherever practical
- In-memory rooms and authoritative simulations
- No database, Redis, Kubernetes, API Gateway, CloudFront, or load balancer for the MVP

Document DNS configuration, inbound ports, certificates, deployment commands, logs, rollback, and cleanup.

Do not assume the exact GoDaddy domain name is known. Use environment variables and placeholders.

Provide an independent local development workflow.

Verify important technical assumptions against current official documentation where available.

## 4. Planning requirements

Read and follow every relevant requirement in `master-prompt.md`, including the complete gameplay rules and the 24-hour hackathon constraint.

Resolve remaining gameplay ambiguities with explicit, simple engineering decisions.

Prioritize:

1. A working end-to-end vertical slice
2. Reliable physical phone controls
3. Clear authoritative simulation contracts
4. Continuous integration between developers
5. Four-phone multiplayer
6. Role switching and full match completion
7. Multiple synchronized screens
8. A reliable AWS-hosted demonstration

Do not overengineer.

## 5. Required files

Create all 18 files:

```text
plans/
├── README.md
├── 01-architecture.md
├── 02-game-specification.md
├── 03-api-contracts.md
├── 04-repository-structure.md
├── 05-development-roadmap.md
├── 06-integration-and-testing.md
├── 07-risks-and-fallbacks.md
├── 08-deployment-runbook.md
├── 09-demo-plan.md
├── teams/
│   ├── playcanvas-richard-ryan.md
│   ├── motion-morteza-tysen.md
│   └── backend-alan.md
└── agents/
    ├── richard.md
    ├── ryan.md
    ├── morteza.md
    ├── tysen.md
    └── alan.md
```

Keep the required filenames, including `playcanvas-richard-ryan.md`, even though Richard now owns the server-side simulation.

## 6. Critical shared contracts

Before creating individual agent briefs, finalize and document:

- REST endpoints and WebSocket paths
- Complete message schemas and event names
- Request/response and broadcast directions
- TypeScript interfaces and corresponding Python Pydantic schemas
- Normalized Arms and Legs input structures
- Coordinate systems and gameplay constants
- Player and room identity
- Lobby and match state machines
- Authoritative simulation interfaces
- Input validation and disconnection behavior
- Snapshot format and broadcast frequencies
- Interpolation and stale-state handling
- Role switching and recalibration
- File ownership and cross-module dependencies

`plans/03-api-contracts.md` must be the single authoritative source of network message schemas.

`plans/02-game-specification.md` must be the single authoritative source of gameplay rules and constants.

Ensure every individual coding agent uses these same contracts. No agent should invent its own incompatible interfaces.

## 7. Parallel development

Structure the plans so all five developers can start immediately after the contract freeze.

Require production-compatible mocks:

- Richard can simulate fake player commands without FastAPI.
- Ryan can render mock authoritative snapshots without a live backend.
- Morteza and Tysen can test and visualize sensor outputs independently.
- Alan can test networking with synthetic game inputs and mock snapshots.

Prioritize the first real end-to-end vertical slice:

**Real phone → motion command → FastAPI → Python simulation → authoritative snapshot → PlayCanvas character movement.**

This should be demonstrated as early as realistically possible.

Include precise milestone acceptance criteria, integration windows, risk-based fallbacks, and a feature-freeze deadline.

## 8. Individual coding-agent briefs

Every agent file must be independently executable.

Include:

- Developer and team identity
- Exact scope
- Files/directories owned
- Interfaces consumed and implemented
- Ordered implementation tasks
- Explicit exclusions
- Mocking strategy
- Testing instructions
- Acceptance criteria
- Definition of done
- Integration responsibilities
- Required handoff information

Make these instructions sufficiently concrete that five separate Codex sessions can implement their assigned work without redesigning the architecture.

Prevent overlapping file ownership.

## 9. Verification and quality

After generating the files, perform a complete consistency audit.

Check that:

1. All 18 documents exist and contain substantive, actionable content.
2. Richard exclusively owns the authoritative gameplay simulation.
3. Ryan owns PlayCanvas rendering.
4. Alan owns networking and infrastructure, not gameplay mechanics.
5. All gameplay mechanics remain server-authoritative.
6. Every required WebSocket event is specified.
7. Python and TypeScript message contracts agree.
8. No agent has conflicting file ownership.
9. All dependencies and integration handoffs are explicit.
10. Mock implementations match production interfaces.
11. HTTPS/WSS deployment works conceptually with the GoDaddy domain.
12. The schedule is appropriate for five developers and approximately 24 hours.
13. Every MVP feature has an owner and an acceptance test.
14. The instructions in every agent file are sufficiently detailed for implementation.
15. No unnecessary infrastructure or nonessential features are introduced.

Correct any inconsistencies you discover.

Do not implement the application. **Only create the complete planning package.**

## 10. Final response

Once every planning file has been written and audited, report:

- The files created
- Final architecture
- Final developer assignments
- Critical path
- First integration milestone
- What each developer should do in the first 60 minutes
- Exact order in which to distribute documents to coding agents
- Any unresolved technical risks or externally unverified assumptions

**Execute now. Do not ask clarifying questions. Make sensible decisions and document your assumptions.**
