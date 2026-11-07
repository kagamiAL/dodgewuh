# Alan — dodgewuh handoff

Updated 2026-11-07. The setup is working; the first functional milestone is still
in progress. Read Git status before editing. The SQL setup was committed as
`9c2a38a`; subsequent readability/bootstrap cleanup may be uncommitted.

## Working and verified

- [x] Python 3.12/uv backend with FastAPI, Uvicorn and Pydantic v2.
- [x] SQLAlchemy 2.1.8, psycopg 3.3.8 (binary) and Alembic 1.20.1 installed and
  locked in `backend/uv.lock`. No automated test dependencies.
- [x] Docker Compose starts coordinator, game worker and PostgreSQL 17.11 healthy.
- [x] Coordinator `localhost:8000` and worker `localhost:8001` serve health,
  Swagger docs and OpenAPI. Health is HTTP liveness only, with `rooms: 0`.
- [x] Coordinator can reach worker over Docker networking. A read-only SQLAlchemy
  query from coordinator reaches database `dodgewuh` through psycopg.
- [x] Local PostgreSQL uses a named volume and has no published database port.
- [x] Terraform and production Compose prepared for two t3.small EC2 VMs in
  us-east-2, Caddy, encrypted disks, coordinator EIP, private worker ingress and
  Session Manager administration without inbound SSH.
- [x] PostgreSQL production data uses an independent encrypted 8 GiB EBS volume,
  deleted along with the stack by terraform destroy. Bootstrap identifies/mounts it by volume
  ID before starting Docker. AWS boot and mount behavior have not been exercised.
- [x] Terraform formatting/validation and read-only plan passed: **21 additions,
  0 changes, 0 deletions**. Saved plans and local state are ignored by Git.
- [x] Production Compose configuration and bootstrap shell syntax checks passed.

## AWS and DNS status

AWS CLI and Terraform are installed under Alan's user directory. CLI default is
us-east-2. Authentication was verified as root in account 127471246523; a dedicated
non-root operator identity has not been configured. The checked regional vCPU
quota was 5, enough for the two planned t3.small VMs (4 total vCPUs).

Domain dodgewuh.fit uses Porkbun DNS; operator DNS edit access is unconfirmed.
**No AWS resources were applied and no DNS records were changed by this work.**
Image publishing, actual VM bootstrap, production secrets, migrations, public TLS
and real-phone WSS/gameplay remain deployment work.

## Decisions to preserve

- User-approved Docker coordinator/worker separation and PostgreSQL override older
  no-container/no-database/single-process planning assumptions. See
  [persistence amendment](../11-sql-persistence.md).
- Coordinator owns SQL writes and membership. Workers import Richard's pure
  simulation and can host multiple rooms; each room has one serialized runner.
  Richard's simulation must not import database, FastAPI or networking libraries.
- Keep live game state, sensor streams, sockets and tick queues in memory. Persist
  room/member metadata, token hashes, allocation metadata and final results as
  features are built. Do not write every simulation tick to SQL.
- Persistence does not provide active-match resume. The current amendment ends
  runtime sessions/aborts interrupted games while retaining SQL records.
- Public schemas come from plan 03. No temporary API/message variants.
- Do not create automated tests, test files or test-only dependencies. Use manual
  verification, builds/type checks and runtime validation.
- Keep documentation changes focused. The prior room-registration subagent was
  stopped; no in-memory rooms.py implementation was integrated. Its scratch work
  under /tmp is not a dependency and should not be relied on.

## Next functional slice — in order

1. Read [Alan brief](alan.md), [API contracts](../03-api-contracts.md) and
   [persistence plan](../11-sql-persistence.md), plus applicable repository rules.
2. Implement database settings/connection management in backend/app, including
   PG* development settings and explicit DB_PASSWORD_FILE reading in production.
   Current FastAPI apps do not read database configuration or create engines.
3. Initialize Alembic and add initial room/member models and migration. Include
   migrations/config in the Docker image and provide a repeatable migration
   command; current Dockerfile copies only app and simulation. Run migrations
   explicitly once per deployment, not on every app startup.
4. Implement agreed protocol models; app/protocol.py currently contains only
   Health. Implement SQL-backed create/join, transactional host/phone registration,
   secure token hashes, code uniqueness, capacity/expiry rules and room count.
5. Manually check migrations, create/join/error/capacity behavior and persistence
   across container recreation. Row retention and backup/restore are unverified.
6. Implement WebSocket session.hello/welcome and full-state baseline, then worker
   allocation/routing, internal authentication and real Simulation integration.

Backend/root/infra/deploy are Alan-owned; do not edit Richard's simulation or
Ryan's frontend dependency manifests. Keep scope small and runnable.

## Known deployment limits

Production app-to-database secret loading, migrations, SQL readiness checks,
worker routing/authentication and frontend deployment are not implemented. A
retained disk is not a backup. Gracefully stop PostgreSQL and take an off-host
backup before VM replacement; verify restore separately. One Terraform destroy
removes the full stack, including PostgreSQL data; no protection needs disabling. See
[infra/README.md](../../infra/README.md) for deployment commands and cleanup.
