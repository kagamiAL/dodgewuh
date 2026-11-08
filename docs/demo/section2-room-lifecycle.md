# Section 2: backend room lifecycle

Implemented in the commit containing this record. Local verification only; no deployment claim.

The coordinator serializes registration, socket attachment, input forwarding and
cleanup decisions with one async lock. An authenticated worker-channel inspection
barrier drains earlier commands before SQL registration policy reads the phase.
SQL runs in a thread, outside the worker tick. Screens remain joinable during play.

Authenticated DELETE revokes the credential and nulls its SQL slot. The worker
removes membership/status, aborts on required-device loss and reconciles lobby
assignments, preserving occupied roles and filling canonical vacancies. Host leave
closes the room. Simulation set_assignments now treats the supplied mapping as
complete, allowing omitted members to release their seats.

Cleanup runs every second. Unconnected registrations and disconnected lobby seats
expire after 30 monotonic seconds; host expiry closes the room. Empty rooms expire
after five minutes, idle lobbies after 30 minutes and all rooms after four hours.
Expiry revokes memberships, emits room.closed where possible and cancels the
coordinator channel, worker runner and peer sender tasks. Runtime deadlines are
not persisted or resumed after coordinator restart.

Local verification on 2026-11-08 UTC (2026-11-07 in Edmonton):

- Backend compileall and git diff --check passed.
- Existing simulation diagnostics: 262/262 observations passed.
- Shared valid/invalid Python protocol fixtures passed.
- Direct runtime checks passed: replacement isolation, required-phone replacement
  abort/readiness clearing, membership removal and canonical vacant-role refill.
- Frontend typecheck and production build passed (existing large chunk warning).
- Rebuilt local Compose coordinator/worker against existing PostgreSQL. Public
  REST/WebSocket checks passed for four-phone capacity, authenticated phone leave,
  revoked-token rejection, replacement registration and host closure. Both health
  endpoints subsequently reported zero rooms, confirming worker runner removal.

Additional checks before commit:

- Routed four-screen capacity and INVALID_PHASE phone rejection during active play
  passed. A late screen received matching active-phase Room/State assignments.
- Routed host-only, wrong-role, stale epoch/assignment/sequence checks passed.
  ready=false, required-device loss and socket replacement returned to lobby,
  cleared readiness and required a fresh start. Replacement accepted input seq=1;
  the superseded socket closed 4409 without detaching its replacement.
- Real 30-second disconnected-phone expiry passed: SQL revoked membership and
  released its slot, the worker removed its assignment, and rejoin filled the
  canonical vacant role. Hard expiry, using a backdated SQL timestamp on only the
  verification room, emitted room.closed(expired), closed sockets, revoked its
  memberships and left the worker with zero rooms.
- Malformed/oversized frames closed 4400; an input-message burst closed 4429.
  Missing/invalid DELETE bearer credentials returned 401.
- Python and TypeScript shared fixtures passed, and the checked-in JSON Schema
  exactly matched both Pydantic envelope exports. No wire schema changed.
- Final isolated-source checks passed for immediate connect/disconnect reservation
  timing and superseded-detach isolation. Service-console checks against dedicated
  PostgreSQL records passed host, empty, idle and unconnected-phone cutoffs using
  backdated monotonic deadlines/SQL timestamps. These are deadline checks, not
  five-minute/30-minute/four-hour wall-clock runs.
- Final backend compileall, simulation diagnostics (262/262), frontend typecheck/
  build, Compose configuration validation and diff whitespace checks passed.

Concurrent section 3/persistence edits appeared during verification. Only section
2 source was selected for this commit; unrelated changes remain in the workspace.
The shared development server reload interrupted the live unconnected-host
30-second check, so that scenario is certified only at the isolated service/SQL
boundary above. Final-source reservation timing was checked separately from the
earlier routed checks. No automated test files or test dependencies were added.

Remaining verification: uninterrupted wall-clock host/empty/idle expiry through the
complete route, exhaustive multi-role transition-bundle ordering, held-ball loss
with real controllers, and browser/device acceptance with the team. The existing
simulation diagnostics still describe the simulation-internal task 8 device-loss
guard as pending; the adapter's explicit abort path passed the routed checks.

## Remaining-check completion — 2026-11-08 UTC

The earlier pending-guard note is historical: Richard's task 8 is merged. This
follow-up uses HEAD `8f2b17eba31bde1aeff6b32ca1fbf77fc1db5c49` plus the adapter
bundle fix in the commit containing this update. Richard's diagnostics pass
**413/413 observations** under Python 3.12, including the simulation-owned guard.

A manual controlled adapter probe exposed a winning-round discrepancy: although
`phase.changed(role_switch)`, `roles.changed`, `room.updated`,
`phase.changed(match_end)`, `room.updated` were ordered correctly, both room
updates used the final match_end state. The adapter now builds each transition's
room update from that transition's captured StateDTO. No simulation rule or wire
schema changed. The same probe now passes for ordinary and winning rounds,
including matching phase/assignment versions, with only the final snapshot.

Final frozen image: `dodgewuh-section2-final:local`, local image ID
`sha256:0d71bb2ba05c02850706127935e08af8d61f1af780a2d35b64bf593ba18b373c`.
BUILD_SHA on coordinator/workers: `8f2b17e-section2-final`. Adapter file SHA-256:
`2fa973964806f425269c4c9fa28834a89eccaffd2a1520ffab7a2f51ceb3ed05`.
These identify the verified image/source; the BUILD_SHA label is not a clean Git
commit. Rebuilding from later source requires new verification.

Used a separate Compose project `dodgewuh-section2-final`, fresh PostgreSQL 17.11
volume, coordinator and two workers, one process per service, no reload/source
mounts. Explicit Alembic upgrade reached `0002_history` before coordinator startup.
REST/WS used `127.0.0.1:20000`, worker health ports 20001/20002, Origin
`http://localhost:5173`, wildcard origins disabled. All participants were synthetic
HTTPX/WebSocket clients. Every received server envelope was validated against the
public protocol model. Existing development containers were left unchanged.

Retained topology: [section2-final-local.compose.yaml](section2-final-local.compose.yaml).
Supply isolated `SECTION2_WORKER_SECRET` / `SECTION2_POSTGRES_PASSWORD` in an
external environment file; no credentials are recorded here. Startup sequence:

```sh
docker compose --env-file /tmp/section2-final.env -p dodgewuh-section2-final -f docs/demo/section2-final-local.compose.yaml build coordinator
docker compose --env-file /tmp/section2-final.env -p dodgewuh-section2-final -f docs/demo/section2-final-local.compose.yaml up -d --wait postgres game-worker game-worker-b
docker compose --env-file /tmp/section2-final.env -p dodgewuh-section2-final -f docs/demo/section2-final-local.compose.yaml run --rm --no-deps coordinator /app/.venv/bin/alembic upgrade head
docker compose --env-file /tmp/section2-final.env -p dodgewuh-section2-final -f docs/demo/section2-final-local.compose.yaml up -d --wait coordinator
```

Manual routed observations:

- `ready=false` while holding and moving returned to lobby; ball grounded with
  zero velocity, characters reset to spawn, all phones unready/uncalibrated.
  Epoch stayed stable over subsequent steps; host start without readiness failed.
- Required Arms replacement while holding closed the old socket 4409, cancelled
  Hold and cleared readiness. The old connection's eventual detach left the
  replacement connected. After fresh calibration/readiness/start, replacement
  input seq=1 was accepted and acquired the ball.
- Required Arms disconnect while holding also reset safely. Reconnecting the same
  token restored identity, but host start remained blocked until fresh readiness.
- A screen registered during active play received a welcome with identical
  Room/State phase, assignments and assignment_version.
- Phone `camera.claim` and unclaimed screen movement returned FORBIDDEN. A screen
  claim suppressed the team's phone Legs movement; claimed screen input moved the
  correct character, and releasing the claim restored phone control.
- Two screens observed a complete three-round 3–0 match from real movement,
  pickup and throw commands. Ordinary and winning phase/role/room bundles agreed,
  including role_switch before match_end on the winning tick; observed state
  epochs, assignment versions and ticks never regressed.

Additional direct adapter observations supplement the network checks: commands
from a superseded peer could not enqueue input, consume its replacement's seq,
detach the replacement or abort the active simulation. A persistent camera claim
resolved to the new authoritative Legs member after a role swap. Controlled
geometry/timing in these direct probes is not claimed as network evidence.

Backend compileall, 413-observation diagnostics, direct bundle probes and diff
whitespace checks passed. No automated test files, permanent diagnostic harness
or dependencies were added. Only the isolated verification stack was stopped
with `down` without `-v`; its database volume was retained.

Both previously unchecked section 2 items are now verified at the local backend
boundary. Real-controller/browser acceptance remains with the team. The earlier
host/empty/idle wall-clock limits remain as documented above; no full-duration
five-minute/30-minute/four-hour network run is claimed.
