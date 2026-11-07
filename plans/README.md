# dodgewuh — project plans

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

Build a cooperative motion dodgeball game with four phone players, two shared characters and one or more browser screens. **Success is a working playable match, not polish or infrastructure breadth.** Use basic shapes, simple lean controls, motion-gated fixed-strength throws and full server snapshots. The 19 core deliverables and audit report are plans; no application or infrastructure has been implemented.

This directory already is `plans/`; documents are intentionally not nested under another plans directory. `plan-creation-prompts.md` overrides the original master prompt. Later user instructions prioritize a minimal working MVP and separate Richard’s simulation plan from Ryan’s frontend plan, superseding the original combined-plan filename requirement.

Audit completed; see [findings and corrections](10-planning-audit.md). Owner-separated directories with `.gitkeep` now exist in the parent repository. No implementation agents have started. Freeze these amended contracts before implementation.

## Reading/distribution order

Distribute the shared documents to all five coding agents first, in this exact order: **01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09**. Freeze the shared contracts/ownership at H0.5. Then distribute the relevant workstream/team plan, then individual brief. All five may start implementation after that freeze; do not serialize the five developers. Alan and Richard publish interface scaffolds first, while Ryan/Morteza/Tysen use compatible fixtures.

| Document | Purpose |
|---|---|
| [01 Architecture](01-architecture.md) | Authority boundaries, runtime, verified technical assumptions |
| [02 Gameplay specification](02-game-specification.md) | Sole rules/constants authority |
| [03 API contracts](03-api-contracts.md) | Sole network schema authority, TS/Python, simulation/component seams |
| [04 Repository structure](04-repository-structure.md) | Exclusive ownership, dependencies, local commands, Git |
| [05 Roadmap](05-development-roadmap.md) | 24-hour schedule, scope gates and first-hour tasks |
| [06 Integration/testing](06-integration-and-testing.md) | Production-compatible mocks and all MVP acceptance coverage |
| [07 Risks/fallbacks](07-risks-and-fallbacks.md) | Early validation, cutoffs and responsible owners |
| [08 Deployment runbook](08-deployment-runbook.md) | EC2/Terraform/GoDaddy/Caddy, local TLS, rollback and cleanup |
| [09 Demo plan](09-demo-plan.md) | Short demonstration, rehearsal and honest fallback |
| [Richard simulation plan](teams/simulation-richard.md) | Authoritative Python gameplay |
| [Ryan frontend plan](teams/playcanvas-ryan.md) | Vue/PlayCanvas rendering and shared UI |
| [Motion Team](teams/motion-morteza-tysen.md) | Arms, Legs, shared sensors, actual phones |
| [Backend Team](teams/backend-alan.md) | Alan transport/integration/hosting |
| [Richard brief](agents/richard.md) | Pure Python simulation implementation |
| [Ryan brief](agents/ryan.md) | Vue/PlayCanvas rendering and integration coordination |
| [Morteza brief](agents/morteza.md) | Arms controls |
| [Tysen brief](agents/tysen.md) | Legs controls and shared sensors |
| [Alan brief](agents/alan.md) | FastAPI/network/infrastructure |

## Locked architecture and team

Richard exclusively owns the authoritative pure Python simulation, integrated by Alan into one FastAPI process on EC2. Alan owns rooms, identities, validation, sockets and Terraform/Caddy deployment. Ryan owns Vue 3/TypeScript/Vite + PlayCanvas rendering, lobby/HUD and PhoneShell, and coordinates integration. Morteza owns Arms UI/aim/Hold/gesture/cancel. Tysen owns Legs physical controls, shared permissions/sensor service and device validation. Richard and Ryan have separate workstream plans and coordinate through the shared snapshot contract. Screens never determine game outcomes. GoDaddy DNS points to an Elastic IP; Caddy serves static frontend and HTTPS/WSS on the same origin.

## MVP boundary

Mandatory: private room/code, four real phones, Arms+Legs cooperation, physical aiming/movement and Hold/release, four balls, half-court boundaries/no-throw zones, hit scoring/60-second timeout, role swaps, first-to-three match/rematch, synchronized screens and public AWS HTTPS/WSS. Simple primitives, fixed throw strength and latest-snapshot rendering are acceptable ways to achieve these.

Excluded: sophisticated physics/animations, variable-strength polish, QR generation, accounts, matchmaking, persistence, prediction, reconnect resume, host migration and extra cloud services. A disconnect safely resets to lobby; players ready and restart. Preserve seats briefly, not interrupted gameplay. Emergency local/single-screen demo is a contingency, not a claim that hosted multi-screen acceptance passed.

## Start now

First 30 minutes: read/freeze 01–04 and ownership; Alan/Ryan bootstrap their respective roots, Richard interface skeleton, motion team actual iPhone permission test. First hour tasks for each person are listed precisely in [05](05-development-roadmap.md). Critical dependency chain: secure phone sensors → normalized command → FastAPI adapter → Python simulation → snapshot → visible character → cooperative throw → four phones → scoring/role swap/full match.

First integration milestone **H4**: real phone movement changes authoritative character and visible PlayCanvas screen through final protocol. **H6**: two-phone throw and public HTTPS/WSS. **H8**: four phones. **H10–12**: full match, role swaps and second screen. **H18**: feature freeze; remaining hours fix/rehearse. Alan begins DNS/account checks immediately while the others continue locally.

## Planning audit and limits

Audit checks: all 19 deliverables, ownership exclusions, server-only outcomes, event/schema parity, full-state mocks, role calibration/epoch semantics, reset on disconnect, single-worker deployment, schedule gates and all 24 MVP requirements mapped in 06. No application tests/deployment have occurred; all test outcomes in these plans are acceptance targets.

Official technical references are linked in 01 and 08. Unverified external dependencies: actual domain/account access, regional EC2 quota/AMI, DNS/certificate issuance, real phone/OS sensor behavior, gesture thresholds and venue network latency. All are assigned early experiments. No browser support or health/sustainability benefits are asserted beyond available evidence. If essentials are late, remove optional work first and pair on the failing vertical slice.

Documentation checks and their limits are recorded in [10 Planning audit](10-planning-audit.md). Structural schema parity alone does not establish compatible lifecycle behavior; the audit corrected those seams before handoff. No application tests, device trials or deployment have run.
