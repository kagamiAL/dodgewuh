# dodgewuh — Tech Stack

Four phones and a shared screen control two dodgeball characters. This page maps every
layer of the project, from AWS infrastructure to the browser.

## System overview

```mermaid
flowchart TB
    subgraph Clients["Clients (browsers)"]
        direction LR
        Phone["📱 Phone controllers<br/>Arms · Legs<br/>Vue 3 + DeviceMotion/Orientation<br/>Web Speech + Web Audio"]
        Screen["🖥️ Screen / Spectator<br/>Vue 3 + PlayCanvas 3D<br/>MediaPipe pose (camera Legs)"]
    end

    subgraph CDN["Third-party CDNs (runtime)"]
        MPJS["jsDelivr<br/>@mediapipe/tasks-vision"]
        MPModel["Google Storage<br/>pose_landmarker_full.task"]
    end

    subgraph AWS["AWS · us-east-2 · Terraform-managed VPC 10.42.0.0/16"]
        direction TB
        EIP["Elastic IP"]

        subgraph Coord["EC2 coordinator (t3.small · Ubuntu 24.04 · Docker Compose)<br/>SG: 80/443 from internet"]
            Caddy["Caddy 2.10<br/>Auto-TLS (Let's Encrypt)<br/>serves Vue SPA from /srv<br/>reverse-proxies /api, /ws"]
            CoordApp["Coordinator<br/>FastAPI + Uvicorn (Python 3.12)<br/>rooms · registration · WS relay"]
            PG[("PostgreSQL 17.11<br/>rooms · members · allocations<br/>matches · assignments · results")]
        end

        EBS[("EBS gp3 (encrypted)<br/>Postgres data + Caddy certs<br/>survives VM replacement")]

        subgraph Worker["EC2 game worker (t3.small · Docker Compose)<br/>SG: 8000 from coordinator SG only"]
            WorkerApp["Game worker<br/>FastAPI + Uvicorn<br/>GameHub"]
            Sim["Simulation engine<br/>pure Python<br/>60 Hz tick · 20 Hz snapshots"]
        end

        SSM["IAM role + SSM Session Manager<br/>(no SSH)"]
    end

    Phone -- "HTTPS + WSS" --> EIP
    Screen -- "HTTPS + WSS" --> EIP
    Screen -. "load model" .-> MPJS
    Screen -. "load model" .-> MPModel
    EIP --> Caddy
    Caddy -- "/api/* /ws/*" --> CoordApp
    CoordApp -- "SQLAlchemy 2 + psycopg 3" --> PG
    PG --- EBS
    CoordApp -- "private WS/HTTP<br/>shared-secret auth" --> WorkerApp
    WorkerApp --> Sim
    SSM -.-> Coord
    SSM -.-> Worker
```

## Layer by layer

```mermaid
flowchart LR
    subgraph Infra["Infrastructure & Ops"]
        TF["Terraform ≥1.10<br/>aws ~>6.0 · random ~>3.6"]
        AWSRes["VPC · subnet · IGW · SGs<br/>2× EC2 · EIP · EBS · IAM/SSM"]
        Boot["deploy/bootstrap.sh<br/>(cloud-init user data)<br/>installs Docker, clones repo @ git_ref"]
        Compose["Docker Compose<br/>compose.coordinator.yaml<br/>compose.worker.yaml"]
        TF --> AWSRes --> Boot --> Compose
    end

    subgraph Backend["Backend (backend/)"]
        Py["Python 3.12 · uv (lockfile)"]
        Fast["FastAPI · Uvicorn[standard]<br/>websockets · httpx"]
        Pyd["Pydantic v2<br/>protocol.py models"]
        ORM["SQLAlchemy 2 · psycopg 3<br/>Alembic migrations (0001–0004)"]
        SimPkg["simulation/<br/>engine · geometry · constants<br/>JSON fixtures"]
        Py --> Fast --> Pyd
        Fast --> ORM
        Fast --> SimPkg
    end

    subgraph Contracts["Shared contract (contracts/)"]
        Schema["protocol.schema.json<br/>Protocol v1 (JSON Schema)"]
        Fix["valid / invalid fixtures"]
    end

    subgraph Frontend["Frontend (frontend/)"]
        Build["Vite 8 · TypeScript 6 · vue-tsc<br/>Node 22"]
        Vue["Vue 3.5 · Vue Router 5<br/>reactive stores (session, connection)"]
        Zod["Zod 4 validators<br/>generated/protocol.ts"]
        PC["PlayCanvas 2.23<br/>court · stadium · crowd · ragdoll<br/>first-person hand"]
        Sensors["Phone sensors<br/>throw gesture · jog tracker<br/>pocket frame · voice prompts"]
        Cam["Camera Legs<br/>MediaPipe Tasks Vision (in-browser)"]
        Test["Vitest 5 · jsdom · @vue/test-utils"]
        Build --> Vue
        Vue --> Zod
        Vue --> PC
        Vue --> Sensors
        Vue --> Cam
    end

    subgraph Assets["3D assets (assets/)"]
        Blender["Blender .blend<br/>Python build scripts<br/>→ export_glb.py → .glb"]
    end

    Schema --> Pyd
    Schema --> Zod
    Blender --> PC
    Compose --> Backend
    Compose --> Frontend
```

## Request & game-loop flow

```mermaid
sequenceDiagram
    autonumber
    participant P as Phone (Arms/Legs)
    participant S as Screen
    participant C as Caddy
    participant CO as Coordinator (FastAPI)
    participant DB as PostgreSQL
    participant W as Game worker
    participant E as Simulation engine

    S->>C: GET / (Vue SPA)
    S->>C: POST /api/rooms (create)
    C->>CO: proxy
    CO->>DB: insert room + member, issue registration token
    P->>C: POST /api/rooms/{code}/members
    C->>CO: proxy
    CO->>DB: insert member, issue registration token
    S->>CO: WSS /ws/rooms/{code} (hello → welcome)
    Note over CO,W: First socket in a room allocates it to a worker (round-robin)
    CO->>DB: insert worker_allocations (report_seq = 0)
    CO->>W: open private WS (Bearer GAME_WORKER_SECRET)
    P->>CO: WSS /ws/rooms/{code} (hello → welcome)
    loop Match
        P->>CO: input.arms / input.legs (Zod-validated)
        S->>CO: input.legs (camera facing via MediaPipe)
        CO->>W: relay authenticated commands
        W->>E: step @ 60 Hz
        E-->>W: state + events (PhaseChanged, RolesChanged)
        W-->>CO: snapshots @ 20 Hz + events
        CO-->>S: relay snapshot → PlayCanvas render
        CO-->>P: relay snapshot/events → UI/voice
        opt phase / roles / room changed
            W-->>CO: op=history {seq, phase, assignments, score, winner}
            CO->>DB: lock room row → insert assignments,<br/>open/complete/abort matches, insert results
        end
    end
    alt Worker channel lost / shutdown / room closed
        CO->>DB: end allocation, abort active matches (worker_lost, server_shutdown, …)
    end
```

**How match history is recorded.** History is written throughout the match, not in
one write at the end. The game worker reports to the coordinator, and the coordinator
writes to PostgreSQL.

1. `GameRoom._flush` (`backend/app/services/game.py`) calls `report_history` when the
   phase changes, the roles change, or the room changes.
2. `report_history` (`backend/app/worker.py`) sends only five fields: `phase`,
   `assignment_version`, `assignments`, `score` and `winner`. It skips the report when
   nothing changed. Each report gets a sequence number (`seq`), and the worker queues it
   as `op: "history"` on the private channel to the coordinator.
3. `WorkerRoom.run` (`backend/app/services/workers.py`) receives the report.
   `Rooms.report` (`backend/app/services/rooms.py`) then locks the room row and
   checks that the allocation is still active.
4. `HistoryRepository.report` (`backend/app/repositories/history.py`) ignores reports
   it has already seen and raises an error if a sequence number is skipped. It records
   each new role assignment version in `assignments`. It opens a `matches` row on
   `countdown` or `active`. On `match_end` it marks the match `completed` and inserts
   the winner and score into `results`. A return to `lobby` marks the match `aborted`.
5. `HistoryRepository.end` closes `worker_allocations` and aborts any active match.
   This happens when a worker is lost (`worker_lost`), when the coordinator restarts
   (`server_restart`), when the server shuts down, or when the room closes.

## Stack summary

| Layer | Technology |
| --- | --- |
| Cloud | AWS (us-east-2): VPC, EC2 t3.small ×2, Elastic IP, encrypted EBS gp3, IAM, SSM Session Manager |
| IaC | Terraform (`hashicorp/aws ~> 6.0`, `hashicorp/random ~> 3.6`) |
| Provisioning | cloud-init user data → `deploy/bootstrap.sh` (Docker CE, swap, git checkout, compose up) |
| Containers | Docker, Docker Compose (local `compose.yaml`; prod coordinator/worker files) |
| Edge / TLS / static | Caddy 2.10 (automatic HTTPS, SPA fallback, zstd/gzip, immutable asset caching) |
| Backend runtime | Python 3.12, uv, FastAPI, Uvicorn, websockets, httpx |
| Validation | Pydantic v2 (backend), Zod 4 (frontend), shared JSON Schema in `contracts/` |
| Database | PostgreSQL 17.11, SQLAlchemy 2, psycopg 3, Alembic |
| Game simulation | Pure-Python authoritative engine on the worker (60 Hz tick, 20 Hz snapshots) |
| Frontend | Vue 3.5, Vue Router 5, TypeScript 6, Vite 8 |
| 3D rendering | PlayCanvas 2.23 (+ `.glb` models authored in Blender via Python scripts) |
| Input | DeviceMotion/DeviceOrientation (phones), MediaPipe Tasks Vision pose (screen camera), Web Speech + Web Audio |
| Testing | Vitest, jsdom, @vue/test-utils; JSON contract fixtures; simulation fixtures |
| Build images | `node:22-bookworm-slim` → `caddy:2.10.2`; `python:3.12-slim-bookworm` + uv |
