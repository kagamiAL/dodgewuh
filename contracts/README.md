# Protocol and first integration handoff

Alan’s first independent slice provides SQL registration, protocol v1 models and
an authenticated lobby handshake. It is ready for the first team integration;
it is not a playable match or a production gameplay backend.

## Where code belongs

- `backend/app/protocol.py`: strict Pydantic wire models and event registries.
- `backend/app/api/rooms.py`, `api/ws.py`: HTTP and socket entry points.
- `backend/app/services/rooms.py`: registration/authentication policy and transactions.
- `backend/app/services/game.py`: live rooms — one Simulation, fixed-step runner and bounded senders per room.
- `backend/app/repositories/`: SQL operations; `db/`: configuration and ORM records.
- `frontend/src/generated/protocol.ts`, `validators.ts`: matching types and Zod validators.
- `frontend/src/net/transport.ts`: native browser transport, independent of Vue components.
- `contracts/protocol.schema.json`, `fixtures/`: exported schema and protocol examples.

Ball/State wire models are validated network payloads, not SQL tables. Live game
state belongs to Richard’s simulation in worker memory.

## Run locally

From the repository root:

```sh
docker compose build
docker compose up -d --wait postgres game-worker
docker compose run --rm --no-deps coordinator /app/.venv/bin/alembic upgrade head
docker compose up -d --wait coordinator
```

Coordinator: `http://localhost:8000`; health: `/api/health`; API docs: `/docs`.
Register a host with `POST /api/rooms`, body `{"name":"Main screen"}`.
Register a phone with `POST /api/rooms/{code}/members`, body
`{"name":"Alan","device":"phone"}`. Keep returned credentials private.

Connect to the returned `ws_path`, then send within five seconds:

```json
{"v":1,"type":"session.hello","payload":{"token":"registration-token"}}
```

The response is `session.welcome` with complete Room and State, followed by
`room.updated`. `session.ping` echoes its nonce through `session.pong`.
Origin must equal `PUBLIC_ORIGIN` (default `http://localhost:5173`). Explicit
additional development origins can be supplied through comma-separated
`DEV_ORIGINS`. Query parameters are rejected; tokens go in hello only.

Local Compose explicitly enables `IN_PROCESS_SIMULATION=true`, running each room's
Simulation inside the coordinator. Without that setting the socket refuses upgrade;
production stays refused until worker allocation/routing exists. Readiness, host
start/reset/rematch and Legs/Arms inputs are routed into the simulation (milestone 1).

## Ryan’s Vue integration

Ryan owns the frontend package manifest and Vite setup. The planned dependencies
must include Zod. No frontend manifest or Vue component was changed in this slice.
Vite must proxy both `/api` and `/ws` to the coordinator, enabling WebSocket
forwarding. Transport derives its URL from the browser’s current origin.

```ts
import { WebSocketTransport } from './net/transport';
const transport = new WebSocketTransport();
const unsubscribe = transport.subscribe(message => {
  // Apply welcome/room/state messages to Ryan’s session store.
});
const unsubscribeStatus = transport.subscribeStatus(status => {
  // connected means validated welcome has already reached subscribers.
});
await transport.connect(registration);
// Controllers obtain sequence numbers from transport.nextInputSeq().
// On Vue unmount: unsubscribe(); unsubscribeStatus(); transport.close();
```

Transport never buffers commands across reconnect. It resets sequence on welcome,
retries transient loss with jittered 0.5/1/2/4/5-second backoff, and treats
superseded/auth/policy/room-closed outcomes as terminal. It sends a ping every five
seconds and closes a silent connection after fifteen seconds.

## Manual verification — 2026-11-07

Passed against local Docker services:

- Create/join returned 201 with no-store headers; full welcome had two characters
  and four balls, matching room/state assignments.
- Phone connection and disconnection broadcast room updates; ping echoed nonce.
- New hello replaced an existing socket with 4409; replacement stayed connected.
- Invalid token and wrong first event closed 4401; missing room closed 4404;
  missing hello timed out after five seconds with 4401.
- Wrong Origin and query credentials were rejected before upgrade with HTTP 403.
- Gameplay command returned explicit SERVER_BUSY without starting a match.
- All 15 valid and seven invalid fixtures agreed in Python and TypeScript.
- Strict TypeScript compilation passed. The compiled actual transport completed
  hello/welcome, sequence reset, ping and superseded-client checks against the
  backend using a temporary Node browser shim.

The first live transport attempt used an overlong display name (correctly rejected
422); the next exposed an Origin mistake in the temporary shim. Correcting those
manual inputs produced the successful results above. No project test files,
harnesses or test dependencies were added. TypeScript/Zod/socket verification
packages were installed only under `/tmp`, not in Ryan’s frontend.

## Next team milestone

Richard supplies the specified Simulation/DTO interface. Alan replaces the local
baseline with worker allocation, DTO conversion and serialized simulation routing.
Ryan connects the store, lobby and renderer; controller owners use the shared
Transport and exact generated types. Verify one real phone command reaching the
simulation and visible screen movement before further polish.

Readiness/start/role authorization, input sequence/epoch enforcement, live ticks,
bounded gameplay queues, seat grace/DELETE membership, safe match abort, production
WSS and real-browser/phone acceptance belong to the next slices. Static lobby
entities and the Node check do not establish gameplay or physical-device support.
