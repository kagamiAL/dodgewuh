# dodgewuh — project plans

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

Build a cooperative motion dodgeball game with four phone players, two shared characters and one or more browser screens. These documents began as implementation plans; repository code has since landed, so schedules, ownership scaffolds and acceptance checklists below are historical targets unless they match the current code described here.

The current local implementation has room creation/join, authenticated WebSockets,
readiness and host controls, the Python simulation in the coordinator, 60 Hz
simulation steps, 20 Hz snapshots, phone pocket-jog Legs, screen-camera Legs,
stadium/crowd rendering and a team-specific first-person screen view. The screen
camera uses browser-local MediaPipe pose processing. Arms phone UI is still a
placeholder. Production coordinator-to-worker allocation/routing and deployed
end-to-end gameplay are not established. See the [repository README](../README.md),
[contracts handoff](../contracts/README.md), and [backend operations](../backend/README.md)
for operational status and limitations.

The specifications remain useful for intended game rules and wire contracts.
The milestone timelines and workstream briefs are historical; do not assume a
checklist item or ownership assignment proves the feature exists. Confirm current
behavior in source and the implementation status in the linked handoffs.

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

The plan documents describe proposed workstream ownership. In current code, the authoritative simulation is called from the coordinator for local integration; although a separate worker service exists, room allocation/routing to it is pending. Current screen code includes PlayCanvas rendering, camera control and first-person view. Production AWS hosting and DNS are not evidenced by this repository status.

## MVP boundary

The planned full game includes private rooms, four phones, Arms+Legs cooperation, movement and throwing, scoring, role swaps and rematch. Current Arms phone UI and production deployment are incomplete; physical-device and full-match acceptance must be confirmed separately. Current screen camera can drive a team's Legs role, and screen view can be selected as team 1, team 2 or overview.

Excluded from the original game scope: sophisticated physics/animations, variable-strength polish, QR generation, accounts, matchmaking, durable gameplay state/resume, prediction, host migration and extra cloud services. Room/member registration metadata is persisted. A disconnect resets an underway match to lobby; players ready and restart.

## Original milestone schedule (historical)

First 30 minutes: read/freeze 01–04 and ownership; Alan/Ryan bootstrap their respective roots, Richard interface skeleton, motion team actual iPhone permission test. First hour tasks for each person are listed precisely in [05](05-development-roadmap.md). Critical dependency chain: secure phone sensors → normalized command → FastAPI adapter → Python simulation → snapshot → visible character → cooperative throw → four phones → scoring/role swap/full match.

First integration milestone **H4**: real phone movement changes authoritative character and visible PlayCanvas screen through final protocol. **H6**: two-phone throw and public HTTPS/WSS. **H8**: four phones. **H10–12**: full match, role swaps and second screen. **H18**: feature freeze; remaining hours fix/rehearse. Alan begins DNS/account checks immediately while the others continue locally.

## Planning audit and limits

The original audit reviewed the plan set before implementation. Its checklist and validation record are historical; they are not evidence of current application behavior or deployment.

Official technical references are linked in 01 and 08. Unverified external dependencies: actual domain/account access, regional EC2 quota/AMI, DNS/certificate issuance, real phone/OS sensor behavior, gesture thresholds and venue network latency. All are assigned early experiments. No browser support or health/sustainability benefits are asserted beyond available evidence. If essentials are late, remove optional work first and pair on the failing vertical slice.

The original documentation audit and its limitations are recorded in [10 Planning audit](10-planning-audit.md). That report predates application implementation and must not be used as the current verification record.
