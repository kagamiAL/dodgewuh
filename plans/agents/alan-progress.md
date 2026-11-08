# Alan — current backend integration handoff

Updated 2026-11-07 against `8d7df53` and `f8184e7` (Milestone 2).
This is a source-status update, not a new runtime or deployment verification.

## Implemented

- SQL-backed registration, hashed tokens, ordered seats, expiry and database health.
- Strict protocol v1, generated frontend validators, JSON Schema and fixtures.
- Public authenticated WebSockets, heartbeat, readiness, host controls and input routing.
- One authenticated private coordinator-to-worker channel per room. Workers run
  Richard's simulation at 60 Hz and publish 20 Hz snapshots; SQL stays with the coordinator.
- Worker-loss closure/revocation, coordinator-restart invalidation and retained history.
- Membership DELETE, 30-second lobby reservations, host-expiry closure, five-minute
  empty-room cleanup, 30-minute idle-lobby and four-hour hard expiry.
- Disconnect safely resets gameplay to lobby; valid-token reconnect restores
  identity with fresh calibration/readiness. Superseded sockets cannot detach replacements.
- Host-only rematch at match_end resets score/arena/readiness and retains assignments.
- Allocation, assignment, match/abort and authoritative final-result persistence.
- Mounted physical Arms controller, pocket-jog Legs, screen-camera Legs,
  role-switch readiness UI, stadium rendering and team first-person views.
- Best-of-3: first to two points, maximum three rounds, equal final score is a draw.
  Migration `0003_draw_results` permits a null winner in stored results.

## Verification and remaining work

Local backend routing, lifecycle, physics and persistence checks are recorded in
[docs/demo](../../docs/demo). Those records retain their original SHAs and scope;
they do not establish acceptance of the latest release. The team reports the
integration slice practically complete; no new device check was run for this update.

Alan's remaining non-deployment work is to record a full routed best-of-3 final
SQL result (including a draw), separate rematch identity, and recovery checks on
the chosen release. Existing lifecycle checks already cover backend reconnect and
worker-loss behavior; repeat only as needed for the final release or a defect.
Coordinate public four-device/two-screen rehearsal and hand off the pinned SHA,
known limitations and observed results. No outstanding simulation implementation
is assumed from the historical milestone checklist.

Production frontend hosting, AWS/DNS/TLS deployment, secrets, migration execution,
backup/restore and rollback rehearsal remain deployment work. Caddy currently
serves a placeholder at the root. Never treat infrastructure files as deployment evidence.

## Operation

Use the [root README](../../README.md), [backend operations](../../backend/README.md),
[contracts](../../contracts/README.md) and [infrastructure notes](../../infra/README.md).
Local Compose uses a separate worker and allows wildcard development Origins;
production requires a deliberate Origin policy and matching worker secrets.
Run Alembic upgrade head before coordinator startup. No mid-match resume or
multi-coordinator support is implemented. Do not add automated tests.
