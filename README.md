# dodgewuh

Four phones cooperate to control two characters. A FastAPI coordinator owns room
registration and PostgreSQL records; Richard's pure Python simulation decides the
game. The coordinator allocates each live room to a game worker and relays authenticated
commands, snapshots and events over a private channel. Worker loss closes affected rooms. The screen has
stadium and crowd visuals, an optional team first-person view, and a camera-based
Legs controller. Arms remains a placeholder. See [Local play](#local-play).

## Start local development

Install Docker with Compose. From the repository root:

```sh
docker compose build
docker compose up -d --wait postgres game-worker
docker compose run --rm --no-deps coordinator /app/.venv/bin/alembic upgrade head
docker compose up -d --wait coordinator
docker compose ps
```

| Service | Local access |
| --- | --- |
| Coordinator | http://localhost:8000/docs |
| Game worker | http://localhost:8001/docs |
| PostgreSQL 17.11 | Compose network only; no published host port |

Both services expose `/api/health` and `/openapi.json`. Coordinator health checks
SQL access and reports the open room count; SQL failures return 503. Worker health
still reports HTTP liveness.

```sh
curl --fail http://localhost:8000/api/health
curl --fail http://localhost:8001/api/health
docker compose logs -f
```

Edits in `backend/app/` reload both services. Simulation source is mounted in the
worker. Reloads restart the process and close affected live rooms. Rebuild after dependency or Dockerfile changes.

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

Database configuration, the initial room/member migration and transactional
create/join endpoints are implemented. Production explicitly reads
`DB_PASSWORD_FILE`; development uses `PGPASSWORD`. See [backend operations](backend/README.md)
for directory boundaries, migration and backup commands.

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

See [the transport handoff](contracts/README.md). Keep public message schemas
unchanged. Do not create automated tests or test-only dependencies; use manual
checks, builds/type checks and runtime validation.

## Local play

The local vertical slice supports room creation/join, readiness, host start/reset,
camera claims, Legs movement, and simulation snapshots. Rooms run at 60 Hz and
screens receive snapshots at 20 Hz in `backend/app/services/game.py`.

1. Start the backend as above. If host port 8000 is taken, set `COORDINATOR_PORT`
   (e.g. `8010`) for `docker compose up`.
2. Frontend (Node 22, see `frontend/.nvmrc`):
   ```sh
   cd frontend && npm ci && npm run dev    # BACKEND_URL=http://127.0.0.1:8010 if you moved the port
   ```
3. Phones need HTTPS for browser camera and motion access. Run a trusted HTTPS
   tunnel to port 5173 (for example `cloudflared tunnel --url http://localhost:5173`).
   Local Compose allows any Origin for hackathon testing; do not copy that setting
   into production.
4. On a laptop open `http://localhost:5173`, **Create room**; the screen shows the code.
5. Fill three phone seats with synthetic ready controllers (they send no input):
   ```sh
   docker compose exec coordinator /app/.venv/bin/python -m app.devtools.synthetic_phones CODE --count 3
   ```
6. On an iPhone open the tunnel URL, join with the code as **Phone**, tap **Ready**,
   then set up Legs: tap Start, allow motion access, pocket the phone, and follow
   the spoken instruction to face the screen and jog in place. The pocketed phone
   is needed even when a screen camera steers that team's Legs.
7. If using four real phones, fill the remaining three seats instead of running
   the synthetic-phone command above. Arms is currently a placeholder and cannot
   aim or throw; the development-only stand-in can report ready for movement
   demonstrations. When all four seats are ready, the host can start. Legs
   movement drives its team's character.

### Camera-driven Legs and screen view

On `/screen`, choose a team in the camera panel and allow camera access. The
preview identifies the Legs player in its right half and tracks which way they
face. The player still pockets their Legs phone, which detects jogging (about
0.3 s, far sooner than pose landmarks can). While the phone reports jogging, the
server moves the character in the camera's facing direction; if the camera loses
the player, it falls back to the phone's own heading. Stop camera sharing or
choose no team to release the claim. Each screen can also view from the team it
drives; use `?view=fp1`, `?view=fp2`, or `?view=overview` to override the default.
These options affect local rendering only. Camera/MediaPipe access requires HTTPS
on phones and the browser downloads MediaPipe assets from jsDelivr and Google.

The simulation includes ball pickup/throws, scoring and role switching. The phone
Arms interface is not implemented yet, so those mechanics do not currently have a
complete physical phone control path.
