# dodgewuh — PostgreSQL persistence and deployment amendment

> Planning amendment, not a current implementation report. Room/member registration, migrations, database health readiness, password-file support and local Compose are implemented. Local live simulations still run in the coordinator; worker allocation/routing and production deployment remain pending. Use [backend operations](../backend/README.md) and [infrastructure status](../infra/README.md) for current details.

This user-approved plan supersedes earlier no-database, single-process and
systemd-backend assumptions. It does not change the REST/WebSocket payloads in
03 or Richard's pure simulation interfaces. Do not create automated tests or
test-only dependencies; use manual checks, builds and runtime validation.

## Deployment topology

Local Docker Compose runs coordinator, game-worker and PostgreSQL. Production
runs coordinator/Caddy/PostgreSQL on one EC2 VM and the game-worker on a separate
VM, initially us-east-2, with dodgewuh.fit as the public origin. A worker may host
multiple rooms, each with one authoritative Simulation and serialized runner.
The coordinator assigns each room to exactly one worker and routes public
same-origin /api and /ws paths. Routing and allocation are not implemented yet.

Use PostgreSQL 17.11 for this milestone, matching local and production images.
PostgreSQL listens only inside the coordinator Compose network; do not publish
5432 or allow workers/browsers direct SQL access. The coordinator owns SQL writes;
workers report completed results through an authenticated internal coordinator
interface to be implemented. The worker needs no database credentials.

## Persistence boundary

Persist room identity/code/host, member records and token hashes, assignments,
worker allocation metadata, match lifecycle records and completed results. Keep
raw tokens out of stored snapshots/logs. Keep physical sensor samples, movement,
ball positions, live sockets, rate-limit windows, heartbeat timers, command queues
and the 60 Hz simulation exclusively in memory. SQL is not a gameplay authority.
Do not perform blocking SQL operations inside the simulation tick.

Persistence preserves records; it does not implement active-match resume. On
coordinator restart, retain saved records and completed results, mark interrupted
matches aborted, invalidate former runtime sessions and require a new lobby/room
flow. Worker loss invokes the existing safe abort behavior; do not reconstruct or
resume a mid-flight simulation from SQL. Rejoin/recovery UX must distinguish saved
history from a currently connectable room. Original runtime room/token grace and
TTL rules remain in force; persistence is not indefinite token authorization.

## Application work, owned by Alan

SQLAlchemy 2, psycopg 3 and Alembic are installed and locked with uv. Configure
them when building persistence-backed room registration. Use PGHOST, PGPORT, PGDATABASE and PGUSER; local dev uses PGPASSWORD,
production reads DB_PASSWORD_FILE. DB_PASSWORD_FILE is application configuration,
not an automatically understood PostgreSQL driver variable: explicitly read it.
Connection code, models, migrations and SQL-backed registration are implemented. Coordinator health checks the database and reports active room count; SQL failures return 503. Live simulations remain in memory and are lost on coordinator restart.

Use tables for rooms, members, assignments, worker allocations, matches and
results, with UUID keys, foreign keys and uniqueness for room codes, occupied
slots and one final result per match. Room+host creation must be one transaction;
phone-slot allocation must be transactionally serialized per room. Duplicate
result callbacks must not award duplicate scores or duplicate final records.
Use UTC timestamps for persisted expiry; never persist process-monotonic time as
an expiry timestamp. Runtime TTL/rate checks can continue using monotonic clocks.

Migrations are versioned under backend/migrations and run explicitly before
starting the new coordinator image, once per deployment. Do not reset/create all
tables on each app startup. Start with room/member registration and expiry, then
allocation and final results as those features exist. Avoid speculative tables
for features outside the MVP. Richard's simulation imports no SQL/framework code.

## Storage and credentials

Development uses the postgres_data Docker named volume, retained across
`docker compose down`; `docker compose down -v` deletes it. The example password
is local-only and must never be used in production. Changing POSTGRES_PASSWORD
only initializes a fresh database; existing passwords require ALTER ROLE.

Production uses a separate encrypted 8 GiB gp3 EBS disk, attached to coordinator
and mounted at /opt/dodgewuh/data. PostgreSQL binds its postgres subdirectory.
VM replacement reattaches this disk in the same availability zone. A full
`terraform -chdir=infra destroy` deletes it, including all PostgreSQL data. Bootstrap identifies it by EBS volume ID and
formats only a raw blank disk. Docker requires the mount at boot. Before replacing
the coordinator, stop its containers and take a backup; Terraform attachment
ordering does not provide graceful database shutdown or application consistency.

Store the production password in an operator-created file outside Git, Terraform
variables/state and EC2 user data. Mount it with Compose secrets into coordinator
and PostgreSQL. Password file must be readable by the unprivileged app container;
use a root-owned 0700 parent directory and a 0444 secret file, so the host path is
protected while the mounted file can be read inside the container. Compose secrets
are file mounts, not an external secret vault. Do not bake passwords into images.

A retained volume is not a backup. Take pg_dump backups and copy them off the VM
before replacement/deletion; verify a restore into a disposable separate database.
EBS snapshots complement this; stop PostgreSQL for a consistent disk snapshot.
This hackathon topology has a single database and coordinator failure domain.
No RDS, extra database VM, NAT gateway or automatic scaling is added here.

## Manual acceptance and handoff

1. Compose starts all three services healthy; psql connects to dodgewuh.
2. Write a temporary record, recreate PostgreSQL and verify the record remains;
   remove the temporary record afterward. No automated test files are needed.
3. Verify production Compose exposes no database port and worker has no SQL secret.
4. Terraform fmt/validate/plan includes the encrypted disk and attachment; do not
   apply until the plan is reviewed. AWS boot/mount behavior needs a deployed VM.
5. After room persistence implementation, create/join, restart coordinator and
   verify records/results remain while previous runtime matches are safely ended.
6. Document migration command, backup/restore procedure and any unverified paths.

The proposed production worker allocation and completed-match persistence remain future work. See the current status note above before using this topology as an operational runbook.
