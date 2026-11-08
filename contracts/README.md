# Protocol and integration status

Protocol v1 is implemented in the backend and generated frontend validators. This
folder contains the JSON Schema and shared fixtures. The authoritative design and
message definitions are in [plan 03](../plans/03-api-contracts.md); gameplay rules
are in [plan 02](../plans/02-game-specification.md).

## Current implementation

- Room create/join, registration tokens, authenticated WebSocket welcome, room
  updates, ping/pong and disconnect cleanup are implemented.
- Local Compose and production configuration route rooms from the coordinator to
  a separate authenticated game worker. Simulation advances at 60 Hz and publishes
  snapshots at 20 Hz; the coordinator relays public messages.
- Readiness, host start/reset/rematch, Legs/Arms input routing, state snapshots,
  role changes and gameplay errors are wired through the simulation.
- Screens can claim a team's Legs steering with `camera.claim` and send
  `input.legs` carrying the Legs player's facing (unit vector, zero when nobody
  is tracked). While that facing is fresh (250 ms) and non-zero, a non-zero
  `input.legs` from the team's Legs phone moves in the camera's direction
  instead of the phone's; the phone still decides when the player jogs. A jog
  that turns from back-to-the-screen to facing it without a stop pauses for
  500 ms, so players don't carry straight on into the no-throw zone.
- `Member.camera_team` reports the team's camera claim, or `null` for no claim.
  Team claims are exclusive; the latest screen claim wins.
- The frontend camera uses MediaPipe pose landmarks, locally in the browser, to
  detect the player in the right half of the preview and their facing. Raw video
  and pose samples are not sent to the backend.
- The phone Arms controller is mounted and implements aim, Hold/pickup and
  gesture-gated release/cancel. PhoneShell handles role changes and fresh readiness.
- Authenticated membership DELETE, disconnect/reset, 30-second lobby reservations,
  token reconnect and host-only rematch are implemented. Reconnect restores
  identity, requires fresh calibration/readiness and does not resume gameplay.
- Matches are best of three: two points ends early; otherwise round three ends
  the match, with a null winner for equal scores.

Worker allocation, private shared-secret authentication, coordinator forwarding,
worker-loss closure and SQL allocation/assignment/result history are implemented.
Local backend verification is recorded under [docs/demo](../docs/demo). Full routed
best-of-3 result/rematch persistence and public physical-device acceptance need
a recorded release check. Production frontend delivery and deployment remain work.

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
same normalized world-vector message whether sent by a phone (movement) or an
authorized screen camera (facing).

Keep fixtures aligned with the strict Python and TypeScript validators. Do not
add automated test files or test-only dependencies; verify contract changes with
runtime validation, type checks and manual integration checks.
