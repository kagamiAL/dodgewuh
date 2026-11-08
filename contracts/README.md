# Protocol and integration status

Protocol v1 is implemented in the backend and generated frontend validators. This
folder contains the JSON Schema and shared fixtures. The authoritative design and
message definitions are in [plan 03](../plans/03-api-contracts.md); gameplay rules
are in [plan 02](../plans/02-game-specification.md).

## Current implementation

- Room create/join, registration tokens, authenticated WebSocket welcome, room
  updates, ping/pong and disconnect cleanup are implemented.
- Locally, `IN_PROCESS_SIMULATION=true` runs Richard's simulation in the
  coordinator. It advances at 60 Hz and publishes snapshots at 20 Hz.
- Readiness, host start/reset/rematch, Legs/Arms input routing, state snapshots,
  role changes and gameplay errors are wired through the simulation.
- Screens can claim a team's Legs control with `camera.claim` and send
  `input.legs`. A camera-driven Legs phone is ignored for movement while that
  screen owns the team's camera input.
- `Member.camera_team` reports the team's camera claim, or `null` for no claim.
  Team claims are exclusive; the latest screen claim wins.
- The frontend camera uses MediaPipe pose landmarks, locally in the browser, to
  detect the player in the right half of the preview and jog direction. Raw video
  and pose samples are not sent to the backend.
- Arms input is part of the protocol and simulation, but the phone Arms UI is
  still a placeholder. A dev-only control can mark it ready; it does not aim or
  throw.

Production worker allocation and coordinator-to-worker routing are not connected.
The production worker API is not the live room authority yet. Do not treat the
local Compose simulation path as proof of deployed gameplay.

## Run locally

From the repository root:

```sh
docker compose build
docker compose up -d --wait postgres game-worker
docker compose run --rm --no-deps coordinator /app/.venv/bin/alembic upgrade head
docker compose up -d --wait coordinator
```

The coordinator is at `http://localhost:8000`; health is `/api/health`; API docs
are `/docs`. Create a host with `POST /api/rooms`, body `{"name":"Main screen"}`.
Join a phone with `POST /api/rooms/{code}/members`, body
`{"name":"Player","device":"phone"}`. The returned token is secret and is
sent in `session.hello`, never in a query string. Vite proxies `/api` and `/ws` to
the coordinator. Local Compose permits any Origin for hackathon testing; production
origin policy remains configured separately.

## Protocol maintenance

When changing a wire message, update `backend/app/protocol.py`,
`frontend/src/generated/protocol.ts`, `frontend/src/generated/validators.ts`,
`contracts/protocol.schema.json`, and the relevant fixtures together. The
`camera.claim` client message carries `{ "team": 1 | 2 | null }`; null releases
the screen's claim. It is authorized for screens only. `input.legs` remains the
same normalized world-vector message whether sent by a phone or an authorized
screen camera.

Keep fixtures aligned with the strict Python and TypeScript validators. Do not
add automated test files or test-only dependencies; verify contract changes with
runtime validation, type checks and manual integration checks.
