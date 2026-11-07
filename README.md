# dodgewuh

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

## Backend development

Install Docker with Compose and uv. From the repository root:

```sh
docker compose up --build -d --wait
curl --fail http://localhost:8000/api/health
curl --fail http://localhost:8001/api/health
docker compose logs -f
```

Coordinator docs: http://localhost:8000/docs. Worker docs: http://localhost:8001/docs.
Stop with `docker compose down`. Source edits in `backend/app` reload both services.
After dependency changes, rebuild with `docker compose up --build -d --wait`.

Without Docker, use two terminals:

```sh
cd backend
uv sync --locked
uv run uvicorn app.main:app --reload --port 8000
```

```sh
cd backend
uv run uvicorn app.worker:app --reload --port 8001
```

Manage dependencies with `cd backend && uv add PACKAGE`; commit `pyproject.toml`
and `uv.lock`. Python 3.12 is selected by `backend/.python-version`.

## Architecture amendment

Docker Compose runs a coordinator and a game worker as separate processes with
network isolation, approximating separate production VMs. The coordinator will
create rooms and allocate them to workers; each room has exactly one authoritative
worker. A worker can eventually hold multiple room simulations. Worker placement
and room registration are not implemented in this scaffold. `GAME_WORKER_URL`
reserves the internal service address; it is not yet consumed by the application.
Health currently reports zero rooms because room storage is not implemented.

This user-approved direction supersedes the single-process/no-container deployment
assumptions in plans 01, 08 and Alan's brief. Gameplay rules and public message
schemas remain as specified. Preserve the public same-origin `/api` and `/ws`
paths through routing/proxying; internal worker addresses must not reach browsers.
Room allocation, authenticated internal calls, WebSocket routing and worker-loss
handling are the next integration decisions. No worker migration or automatic VM
provisioning is included yet.

Compose is for local development: loopback ports, source mounts and reload enabled.
Production will run coordinator and worker containers on separate VMs, without
reload, behind Caddy HTTPS/WSS, with private authenticated service communication
and one Uvicorn worker per container. This scaffold does not provision those VMs.

## AWS infrastructure

See [infra/README.md](infra/README.md) for the two-VM Terraform configuration,
production Compose files, deployment prerequisites and cleanup instructions.
