# Project integration status

Updated 2026-11-07 at `9464caa` (`first person view`). This replaces the old
"first independent milestone" handoff; that text described an earlier lobby-only
slice. See [the root README](../../README.md), [backend operations](../../backend/README.md),
[protocol handoff](../../contracts/README.md), and [infrastructure notes](../../infra/README.md)
for current usage and limitations.

## Implemented in the current tree

- SQL-backed room/member registration, hashed tokens, ordered initial seats,
  migrations, expiry cleanup and database readiness.
- Strict protocol v1 models, generated TypeScript types/validators, JSON Schema
  and valid/invalid fixture examples. `camera.claim` and `Member.camera_team` are
  part of the current wire shape.
- Authenticated WebSocket hello/welcome, room updates, heartbeat, input routing,
  host controls, readiness, gameplay errors and disconnect handling.
- In local Compose, one Richard `Simulation` runs per room inside the coordinator
  with a 60 Hz runner, bounded senders and 20 Hz snapshots. The separate worker
  container is not used for live room routing.
- Phone Legs can jog in place while the phone is pocketed. A screen can claim a
  team's Legs input and use its camera with browser-local MediaPipe pose tracking.
- The screen renders stadium/crowd/floor visuals and supports overview or a
  team-specific first-person view. Mobile layouts and sensor playground are in
  the frontend.

## Known incomplete work

- `ArmsPending.vue` is still the phone Arms UI. It cannot aim or throw; a dev-only
  stand-in only reports readiness. Although the simulation/protocol include Arms
  commands and ball gameplay, the complete physical control path is unfinished.
- Production coordinator-to-worker allocation, WebSocket forwarding, worker API
  authentication, worker-loss handling, frontend hosting and deployed gameplay
  are not wired. Terraform and deployment Compose files are infrastructure plans,
  not proof of an applied deployment.
- Do not infer real-phone/browser compatibility, successful full-match acceptance,
  or production hosting from this repository's implementation alone.

## Local operation

Use the root [README](../../README.md) for Compose and frontend startup. Local
Compose sets `IN_PROCESS_SIMULATION=true` and permits any Origin for hackathon
access; production must use a deliberate origin policy. `backend/README.md`
contains migration, registration and database details. The early M1 simulation
notes in [HANDOFF.md](../../backend/simulation/HANDOFF.md) are historical.
