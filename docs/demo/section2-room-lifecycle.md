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
