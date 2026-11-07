# Coordinator persistence

Directory boundaries:

- `app/db/`: coordinator-only configuration, engine/session factory and ORM records.
- `app/repositories/`: room/member queries, inserts and database locks; no commits.
- `app/services/`: registration rules, expiry policy and shared transaction boundaries.
- `app/api/`: public HTTP routes and process-local rate limits.
- `app/protocol.py`: strict public wire models implemented so far.
- `migrations/versions/`: immutable, explicit Alembic schema revisions.
- `app/worker.py` and `simulation/`: worker entry point and Richard-owned pure simulation.

Run one coordinator process. Startup closes previous runtime rooms and revokes
old memberships, retaining records. Do not overlap coordinator instances or use
multiple Uvicorn workers. Local auto-reload also ends rooms. There is no match
resume. Slot order 0–3 maps to T1 Arms, T1 Legs, T2 Arms, T2 Legs when the worker
adapter is implemented. Initial slot membership is durable; role swapping will
come from the simulation, not registration SQL.

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
Do not paste responses into logs or commit them. `ws_path` is the agreed future
socket route; WebSocket authentication/welcome is not implemented yet. DELETE
membership, connection grace, empty-room TTL and worker allocation remain part of
the transport slice. Registered lobbies expire after 30 minutes without activity
and all rooms after four hours. Cleanup runs every 30 seconds and during health
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
