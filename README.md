# dodgewuh

Four phones cooperate to control two characters. A FastAPI coordinator owns room
registration and PostgreSQL records; a separate game worker runs Richard's pure
Python simulation. The current implementation is a working service scaffold.

## Start local development

Install Docker with Compose. From the repository root:

```sh
docker compose up --build -d --wait
docker compose ps
```

| Service | Local access |
| --- | --- |
| Coordinator | http://localhost:8000/docs |
| Game worker | http://localhost:8001/docs |
| PostgreSQL 17.11 | Compose network only; no published host port |

Both FastAPI services expose `/api/health` and `/openapi.json`. Health currently
reports HTTP liveness and `rooms: 0`; the app does not use the database yet.

```sh
curl --fail http://localhost:8000/api/health
curl --fail http://localhost:8001/api/health
docker compose logs -f
```

Edits in `backend/app/` reload both services. Simulation source is mounted in the
worker. Reloads restart the process and will discard live game state once it is
implemented. Rebuild after dependency or Dockerfile changes.

Stop with `docker compose down`. PostgreSQL data remains in `postgres_data`.
`docker compose down -v` deletes that data. The password default is for local
use only. Copy `.env.example` to `.env` if you need overrides; never commit `.env`.

## Python dependencies

Use uv with Python 3.12; `backend/.python-version` selects the interpreter.
Dependencies include FastAPI, Pydantic v2, SQLAlchemy 2, psycopg 3 and Alembic.

```sh
cd backend
uv sync --locked
uv add PACKAGE
```

Commit both `pyproject.toml` and `uv.lock` after a dependency change. To run only
the HTTP scaffold outside Docker, use separate terminals from `backend/`:

```sh
uv run uvicorn app.main:app --reload --port 8000
uv run uvicorn app.worker:app --reload --port 8001
```

The Compose database hostname resolves inside Docker; native database access
needs separate host/network configuration. Use the coordinator container for
current database connectivity checks.

## PostgreSQL

```sh
docker compose exec postgres psql -U dodgewuh -d dodgewuh \
  -c 'SELECT current_database(), version();'
```

PostgreSQL and the Python libraries are installed and reachable. Database
connection code, Alembic configuration, migrations and SQL-backed endpoints are
not implemented yet. Production will read its password from a mounted secret
file; the app must implement `DB_PASSWORD_FILE` handling explicitly.

Live simulation state stays in worker memory. SQL stores room/member metadata,
allocation records and completed match results as those features are implemented.
Persisted records do not imply that interrupted games can resume.

## AWS and implementation handoff

Terraform prepares two EC2 VMs in `us-east-2` and an encrypted persistent database
disk. Production Compose has no reload or source mounts. Caddy provides the
public entry point for `dodgewuh.fit`; Porkbun manages DNS. No resources have
been applied and DNS has not been changed by this setup work.

- [Current progress and next task](plans/agents/alan-progress.md)
- [API contracts](plans/03-api-contracts.md)
- [Persistence and service boundaries](plans/11-sql-persistence.md)
- [Infrastructure and deployment instructions](infra/README.md)

The next slice is database configuration, initial Alembic migrations, SQL-backed
room creation/join and then authenticated WebSockets. Keep public message schemas
unchanged. Do not create automated tests or test-only dependencies; use manual
checks, builds/type checks and runtime validation.
