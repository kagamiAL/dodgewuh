# Alan — first independent milestone handoff

Updated 2026-11-07. Implementation is ready for the first team integration.
See [protocol handoff and manual evidence](../../contracts/README.md) for startup,
module ownership, connection examples, verified results and remaining work.

## Complete for this slice

- SQL-backed room/member registration, hashed tokens, ordered seats, migrations,
  TTL cleanup, database readiness and restart invalidation from the prior slice.
- Strict protocol v1 Python models/event registry, matching TypeScript types and
  Zod validators, JSON Schema and valid/invalid protocol fixture examples.
- Authenticated first-frame hello, complete welcome baseline, Origin checking,
  duplicate socket replacement, heartbeat, membership broadcasts, frame/rate bounds.
- Native browser Transport in Alan’s assigned frontend directories, with validated
  messages, status subscriptions, central input sequence and reconnect behavior.
- Existing split preserved: API entry points → service policy → SQL repositories
  → database models/configuration. No frontend package/Vue files or simulation
  internals changed. No automated tests or project verification dependencies added.

## Verification

Manual Docker checks passed for create/join, welcome, ping, connect/disconnect,
supersession, missing room, bad token/Origin/query credentials and hello timeout.
Python and TypeScript agreed on all 15 valid and seven invalid fixtures. Strict
TypeScript compilation passed; the compiled transport exchanged real messages
with the local backend and handled supersession correctly using a Node shim.
Browser/device, cloud WSS and full matches have not been verified.

The local lobby baseline requires LOBBY_BASELINE_ENABLED=true, enabled only in
local Compose. It cannot start gameplay; gameplay/readiness requests explicitly
return SERVER_BUSY. This is the pre-integration boundary, not the H4 movement gate.

## Milestone 1 integration (2026-11-07)

`app/services/game.py` replaces the static lobby baseline: one Richard `Simulation`
per room, a 60 Hz runner (5-step catch-up, 250 ms overload abort), 20 Hz snapshots,
ordered transition bundles, per-socket bounded senders, readiness mirroring,
host-only controls, per-socket seq checks and room-wide ordinals, and
disconnect/ready=false aborts. It runs in the coordinator behind
`IN_PROCESS_SIMULATION=true` (local Compose only). Verified manually with four
socket clients: start gating, countdown → active, Legs movement at ~3.5 m/s,
20 snapshots/s, WRONG_ROLE/OLD_SEQ rejection and disconnect → lobby.
`app/devtools/synthetic_phones.py` fills seats for the one-real-phone slice.

## Next work with the team

Connect Richard’s Simulation/DTOs through the worker adapter and serialized runner;
connect Ryan’s Vue store/lobby/renderer and the phone controllers. Ryan adds the
planned Zod dependency and API/WebSocket Vite proxy in his owned scaffold.
Then complete authoritative readiness/inputs/lifecycle and real-phone acceptance.

Keep SQL for durable records only, never live ball positions or sensor streams.
Worker allocation/results migrations, disconnect grace, membership DELETE, safe
match abort, production routing/WSS, backup restore and deployment remain pending.
AWS/DNS were not changed by this slice; prior Terraform validation is not deployment.
