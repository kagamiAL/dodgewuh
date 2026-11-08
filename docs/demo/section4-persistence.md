# Section 4 persistence — local verification

Verified 2026-11-08 UTC on the working tree based on `2d057fb`, with the persistence changes in this commit. This is not a deployed release or full-match acceptance.

Migration `0002_history` adds worker_allocations, versioned assignments, matches and results. Registration schema/data remain intact. Run `PYTHONPATH=backend backend/.venv/bin/alembic -c backend/alembic.ini upgrade head` with the coordinator database environment before starting the release. Upgrade is additive; downgrade deletes history and must not be used as an image rollback.

The coordinator saves an allocation before opening its one private worker channel. That authenticated channel carries ordered `history` reports, separately from public messages, for initial assignments, assignment changes and phase boundaries. Reports contain only phase, assignment version/mapping, score and winner. No SQL, sensor samples or trajectories enter the simulation. The bounded relay queue fails closed on overload rather than silently dropping history. SQL writes run serially in coordinator threads outside the worker tick. Channel failure closes the allocation/room and revokes memberships; it never recreates the simulation.

The allocation UUID plus persisted report sequence provides callback identity. Duplicate/older sequences are no-ops; gaps fail the channel. Match UUIDs and allocation-local ordinals distinguish rematches. The first countdown/active report opens a match; lobby aborts it; an authoritative match_end stores its final score/winner once (result primary key is match_id). Persistence does not award gameplay scores. Round/role-switch boundaries retain the same match. Room expiry/host leave/worker loss abort active matches and end allocations. Coordinator restart aborts former matches, closes old allocations/rooms and revokes tokens while retaining history. A crash before a final report commits can leave an aborted rather than completed match; no resume or guaranteed final-result delivery across a lost channel is claimed.

Manual checks used disposable PostgreSQL 17.11 and temporary diagnostics under /tmp; no automated tests or dependencies were added:

- Alembic upgrade head and offline SQL generation passed; Alembic check reported no schema differences.
- Repository/service probes passed: duplicate report no-op, one final result per match, rematch identity, restart retention, interrupted-match abort and rejection of old bearer tokens.
- Separate coordinator/worker processes on loopback ports 58400/58401 passed public REST phone registration, authenticated public WebSocket welcome, private worker assignment reporting into SQL, and durable worker-loss closure.
- An additive 0001 → 0002 upgrade with three retained room rows preserved all three. Downgrade was exercised only in that disposable database, after history checks; the container was removed afterward. Existing development Compose/database were not migrated.
- Backend compileall, migration SQL generation, simulation.synthetic (262/262 observations) and git diff whitespace checks passed.
- Before commit, repeated the migration/schema, duplicate/restart/token and live worker-routing checks after adding serialized allocation creation, channel-end history cleanup and explicit channel closure on report-queue overflow. Full routed completion remains unverified.

Richard's current working-tree simulation emits role-switch and match-end boundaries, and the adapter consumes them. Final-result persistence was verified with injected service reports, not a full routed first-to-three match. Team coordination and full routed completion/role-switch validation remain unverified; do not certify full-match persistence or physical-device acceptance from these checks. The synthetic diagnostic still identifies required-device readiness abort as an outstanding simulation dependency.
