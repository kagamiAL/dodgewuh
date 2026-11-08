# Coordinator persistence

Directory boundaries:

- `app/db/`: coordinator-only configuration, engine/session factory and ORM records.
- `app/repositories/`: room/member queries, inserts and database locks; no commits.
- `app/services/`: registration rules, expiry policy and shared transaction boundaries.
- `app/api/`: public HTTP routes and process-local rate limits.
- `app/protocol.py`: strict public wire models implemented so far.
- `migrations/versions/`: immutable, explicit Alembic schema revisions.
- `app/worker.py` and `simulation/`: worker entry point and Richard-owned pure simulation.

Run one coordinator process and one process per worker. The coordinator pins each
room to one worker over a private WebSocket channel. Set the same nonempty
`GAME_WORKER_SECRET` on both services. `GAME_WORKER_URL` selects the worker;
optional comma-separated `GAME_WORKER_URLS` distributes new rooms round robin.
Only the coordinator authenticates public tokens; workers receive membership facts
and validated commands, never tokens or SQL credentials. Keep worker ports private.
Channels use ping/pong to detect loss; failure closes all affected sockets and
marks the room closed (`worker_lost`) in SQL, revoking memberships. Failed room
allocations remain blocked in memory even if SQL is unavailable. Create a new room
after failure; interrupted games never resume. Empty rooms close after five minutes; room cleanup closes their worker channel
and allocation. Allocation metadata is persisted; live channels/simulations are runtime-only.
Startup closes previous runtime rooms and revokes old memberships, retaining
records. Do not overlap coordinator instances or use
multiple Uvicorn workers. Local auto-reload also ends rooms. There is no match
resume. Initial phone registration slots are in order T1 Arms, T1 Legs, T2 Arms,
T2 Legs; the simulation owns current assignments and swaps roles after rounds.
Worker gameplay runs through `app/services/game.py`.

## Migrations

From the repository root, build first. Run migrations once per release, before
starting the new coordinator; they never run automatically at application startup:

```sh
docker compose build
docker compose up -d --wait postgres game-worker
docker compose run --rm --no-deps coordinator /app/.venv/bin/alembic upgrade head
docker compose up -d --wait coordinator
docker compose run --rm --no-deps coordinator /app/.venv/bin/alembic current
docker compose run --rm --no-deps coordinator /app/.venv/bin/alembic check
```

For production, use the same `run --rm --no-deps coordinator ... upgrade head`
command with `docker compose -f deploy/compose.coordinator.yaml` and the deployment
environment on the coordinator host. Start PostgreSQL first. Coordinate downtime
and take a backup before migrations. Do not run downgrade against retained data
as an image rollback step; `0001` downgrade removes registration tables.

Connection configuration: `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and local
`PGPASSWORD`. When `DB_PASSWORD_FILE` is set, its contents take precedence;
missing/unreadable/empty files fail startup. Trailing newlines are stripped,
other password characters are preserved. Never log a URL or secret. Workers do
not initialize a database engine and receive no SQL credentials.

## Registration

```sh
curl -i -H 'Content-Type: application/json' \
  -d '{"name":"Main screen"}' http://localhost:8000/api/rooms
curl -i -H 'Content-Type: application/json' \
  -d '{"name":"Alan","device":"phone"}' \
  http://localhost:8000/api/rooms/ABC234/members
```

Registration returns a secret bearer token once; only its SHA-256 hash is stored.
Do not paste responses into logs or commit them. `ws_path` is the authenticated
socket route. The first message must be `session.hello` with the token; welcome
includes complete room and game state. Readiness, host start/reset/rematch, input
routing, snapshots and `camera.claim` are forwarded to the worker.
Authenticated `DELETE /api/rooms/{room_code}/members/me` with a Bearer token
revokes membership and releases its seat; host leave closes the room. Required
phone loss or loss of the last screen resets gameplay to lobby. Disconnected or
unconnected members have a 30-second lobby reservation; an existing valid token
restores identity before expiry, with fresh calibration/readiness required. Host
reservation expiry closes the room. Superseded sockets cannot detach replacements.
Host-only `match.rematch` is accepted at match_end, retains assignments and resets
scores, arena and readiness to lobby; interrupted matches do not resume.
Registered lobbies expire after 30 minutes without activity and all rooms after
four hours. Cleanup runs every 30 seconds and during health
checks; joins independently reject expired rooms. Closed records are retained.

Room+host creation is atomic. An advisory transaction lock serializes the ten-room
cap and code generation; per-room row locks serialize joins, backed by unique
slot constraints. Each device category has four slots, including the host screen.
Create and join enforce 5/min and 30/min per direct peer IP. Configure Uvicorn's
trusted proxy addresses explicitly behind Caddy; never trust arbitrary forwarded
headers. Rate windows live in memory and reset on restart. No automated tests or
test dependencies are included.

## Backup and restore

Local example (use a protected destination outside Git):

```sh
umask 077
docker compose exec -T postgres pg_dump -U dodgewuh -d dodgewuh -Fc > /secure/path/dodgewuh.dump
```

For production use its Compose file and copy the dump off the VM. Verify restore
into a separate disposable database, never over the running application database:

```sh
docker compose exec -T postgres createdb -U dodgewuh dodgewuh_restore
docker compose exec -T postgres pg_restore -U dodgewuh -d dodgewuh_restore < /secure/path/dodgewuh.dump
docker compose exec -T postgres psql -U dodgewuh -d dodgewuh_restore -c 'SELECT count(*) FROM rooms;'
```

Inspect retained records and migration revision before deleting the disposable
restore database. Backup/restore has not yet been exercised. A Docker volume or
EBS disk is not an off-host backup. Terraform destroy still deletes all AWS data.

## Match history persistence

Run Alembic through `0003_draw_results` before starting this release. `0002_history` adds history tables; `0003_draw_results` makes the result winner nullable for best-of-3 draws. Its downgrade deletes drawn results and must not be used for image rollback. The coordinator records allocations, versioned assignments, match starts/aborts and authoritative final results from the authenticated worker channel. Restart preserves history and revokes old sessions; active matches are aborted rather than resumed. See [section 4 verification](../docs/demo/section4-persistence.md) for duplicate-report behavior, migration compatibility and unverified full-match completion.
