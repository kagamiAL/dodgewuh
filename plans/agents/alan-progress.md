# Alan — dodgewuh handoff

Updated 2026-11-07. Git was clean before this slice. Persistence and registration
changes are staged but uncommitted; this handoff update is unstaged. Inspect Git
status before editing, and preserve the user's staging choices. No commit was made.

## Working and verified

- Python 3.12/uv/FastAPI; SQLAlchemy 2, psycopg 3 and Alembic remain locked.
  No dependencies or automated tests were added.
- Separate `backend/app/db`, `app/repositories`, `app/services`, `app/api`
  directories implement database configuration, SQL access, registration policy
  and HTTP routing. Services own shared transactions; repositories never commit.
  Comments and docstrings explain transaction ownership, locks, credentials and
  lifecycle behavior. All earlier verification categories were rerun after this
  separation on rebuilt images; results are recorded below.
- `PG*` development configuration and explicit production `DB_PASSWORD_FILE`
  reading work. Password-file precedence was manually verified without logging
  secrets. Workers receive no SQL configuration and create no database engine.
- Initial room/member schema lives under `backend/migrations/versions` and is
  included in the Docker image with Alembic configuration. Explicit upgrade on
  local PostgreSQL passed. Fresh upgrade, schema-drift check and downgrade passed
  in a separate disposable database, which was removed afterward.
- SQL-backed create/join follows plan 03: atomic room+host registration, UUIDs,
  unique six-character codes, 32-byte random tokens stored only as SHA-256 hashes,
  normalized names/codes, four phone and four screen slots, serialized joins,
  ten-room cap and process-local IP rate limits. Slot order maps to the initial
  assignments when the simulation adapter is built.
- Manual HTTP checks passed for create, lowercase-code join, four phones, fifth
  phone rejection, missing room, malformed request and `Cache-Control: no-store`.
  SQL inspection confirmed trimmed names, slots and token hashes.
- Coordinator health reads SQL and counts open rooms. Stopping PostgreSQL produced
  JSON 503; restarting it recovered to 200. All three services finished healthy.
- Idle-lobby expiry was manually verified by aging a temporary room. Hard expiry
  is enforced at four hours. Cleanup runs every 30 seconds and on health requests.
- Recreating coordinator and PostgreSQL preserved five member records, closed the
  former runtime room and revoked all five memberships. Joining that room returned
  404. Verification records were removed afterward. SQL history is retained in
  normal operation; restart does not implement match resume.
- Docker builds and `git diff --check` passed. Rate thresholds, ten-room saturation,
  concurrent join races and full screen capacity have not been manually exercised.

## Final verification rerun — 2026-11-07, 20:53–20:55 UTC

All checks below passed against the repository/service split:

- Both Docker images rebuilt and all three services finished healthy.
- Existing-database Alembic upgrade and schema check; fresh upgrade/check/downgrade
  in disposable `dodgewuh_handoff_review`, which was dropped afterward.
- HTTP health 200, create/join 201, malformed request 422, absent room 404,
  lowercase-code lookup, four ordered phone seats and fifth-phone 409.
- Membership responses included no-store headers. SQL showed trimmed names,
  phone slots 0–3, host screen slot 0 and 64-character token hashes.
- Password-file precedence checked with a temporary nonproduction value.
- PostgreSQL/coordinator recreation retained five members, closed the former room
  with `server_restart`, revoked all five memberships and rejected the old room.
- Aging a separate temporary lobby by 31 minutes caused `expired` closure and
  health room count zero.
- PostgreSQL stop produced JSON health 503; restart restored health 200.
- Python syntax parsed in all 16 app/migration files; staged and unstaged Git
  whitespace checks passed.

Only the two rooms and six members created by this rerun were removed afterward.
No automated test files, test harnesses or dependencies were created. No AWS/DNS
changes. Rate thresholds, saturation/concurrency, screen capacity, backup/restore
and real-device gameplay remain unverified as described above.

## Run and directory guide

See [backend operations](../../backend/README.md) for directory responsibilities,
configuration, migration commands and backup/restore instructions. From repo root:

```sh
docker compose build
docker compose up -d --wait postgres game-worker
docker compose run --rm --no-deps coordinator /app/.venv/bin/alembic upgrade head
docker compose up -d --wait coordinator
```

Run migrations once per deployment, never per app startup. Use one coordinator
process and do not overlap coordinator instances: startup ends former sessions.
Local auto-reload also ends rooms. The current worker health remains liveness only.
Backup/restore commands are documented but have not been exercised.

## Next functional slice

1. Implement the remaining exact plan 03 protocol models, authenticated WebSocket
   hello/welcome, Origin checks and full-state baseline. `ws_path` is returned by
   registration but the socket endpoint is not implemented. `backend/simulation`
   currently has no implementation to integrate; coordinate Richard's interface.
2. Add runtime connectivity/readiness, DELETE membership, disconnect grace and
   five-minute empty-room expiry with the transport lifecycle. Current registration
   expiry covers idle lobbies and hard TTL; SQL is not live connection authority.
3. Add authenticated coordinator/worker allocation and routing, the real Simulation
   adapter and one serialized runner per room. Mirror assignments from simulation;
   never persist ticks, sensor streams, live positions, sockets or tick queues.
4. Add allocation/match/result migrations as those features exist. No speculative
   tables were added. Verify exactly-once results and safe interrupted-match abort.
5. Complete frontend integration and real-phone WSS/gameplay acceptance. Healthy
   HTTP and successful registration do not establish a functional game.

## AWS and DNS status

Terraform previously validated and planned **21 additions, 0 changes, 0 deletions**
in us-east-2 for coordinator/worker VMs and encrypted PostgreSQL storage. Domain
is dodgewuh.fit; DNS is managed by Porkbun. Nothing was applied or changed in AWS
or DNS during this slice. AWS boot/mount, production secret permissions, image
publishing, TLS and public WSS remain unverified. Configure trusted proxy addresses
explicitly for per-client rate limiting behind Caddy.

A normal Terraform destroy removes the entire stack, including PostgreSQL data;
there is no destruction guard. A retained volume is not a backup. Stop PostgreSQL
and take an off-host backup before VM replacement; verify restore separately.
See [infrastructure instructions](../../infra/README.md).

Preserve ownership: Alan owns backend except Richard's simulation and root/infra/
deploy. Do not edit frontend manifests or simulation internals. No automated tests,
test files or test-only dependencies; use manual checks and focused documentation.
