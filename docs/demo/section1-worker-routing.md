# Section 1 — local worker-routing verification

Completed 2026-11-08, approximately 00:55–01:05 UTC (2026-11-07 in Edmonton).
Verified source: `6b02f9cae29a808650b06190352a255ec5c486e4`.

During this work the shared branch was updated to `0a09b908e9f1bc29d794e33dfa082d6fb5969903`, incorporating Richard's newer round logic and replaying the routing commit. The committed routing backend files match the verified source, but the newer simulation and subsequent concurrent lifecycle edits were not part of the frozen container images checked here. This record is pinned to the verified source rather than claiming verification of every later workspace change.

This is a manual local backend verification record. No public deployment, TLS, browser sensor checks, physical phones, completed-match lifecycle or rollback acceptance is claimed. The existing development containers and their database volume were left alone. No automated test files or test dependencies were added.

## Environment and startup

Built the backend with `docker compose build`; locked dependencies installed successfully. Ran a separate Compose project named `dodgewuh-section1` with a fresh PostgreSQL volume, coordinator and two workers, one Uvicorn process per service and no reload/source mounts. The configuration is retained as [section1-local.compose.yaml](section1-local.compose.yaml); credentials are supplied through environment variables and are not included in this record.

| Service | Local endpoint | Verified build |
|---|---|---|
| Coordinator | http://127.0.0.1:18000 | `6b02f9cae29a808650b06190352a255ec5c486e4` |
| Worker A | http://127.0.0.1:18001 | same |
| Worker B | http://127.0.0.1:18002 | same |
| PostgreSQL | Compose network only | PostgreSQL 17.11; Alembic `0001_registration` |

The public-facing socket route was `ws://127.0.0.1:18000/ws/rooms/{code}` with Origin `http://localhost:5173` and wildcard origins disabled. This is a local WS endpoint, not public WSS. The coordinator used both private worker URLs for round-robin allocation.

Image IDs built from the verified routing source:

- Coordinator: `sha256:48a4b202a390df5a34741691a48722a282647595177ba36a60a68f6b4b30c439`
- Worker: `sha256:e2333a4efc4bc35f6660c116994ce5dcd6e43b113e52b857acae9d029e2d6854`

The images initially ran with BUILD_SHA `section1-working-tree`. After committing the identical routing source, they were tagged `6b02f9c` and the services recreated with the full source SHA. All three health endpoints reported that SHA; fresh REST registration and welcome succeeded again. These are local image IDs/tags, not registry-published release digests.

Startup sequence used (the temporary configuration was subsequently retained and sanitized at the path below):

```sh
# Supply SECTION1_WORKER_SECRET and SECTION1_POSTGRES_PASSWORD in the environment.
# These are isolated local credentials, not production credentials.
docker compose build
docker tag eggwuh-htc-2026-coordinator:latest eggwuh-htc-2026-coordinator:6b02f9c
docker tag eggwuh-htc-2026-game-worker:latest eggwuh-htc-2026-game-worker:6b02f9c
docker compose -p dodgewuh-section1 -f docs/demo/section1-local.compose.yaml up -d --wait postgres game-worker game-worker-b
docker compose -p dodgewuh-section1 -f docs/demo/section1-local.compose.yaml run --rm --no-deps coordinator /app/.venv/bin/alembic upgrade head
docker compose -p dodgewuh-section1 -f docs/demo/section1-local.compose.yaml up -d --wait coordinator
```

Use matching routing source when rebuilding these tags. Changing an existing verification volume's password environment does not rotate its stored PostgreSQL password.

## Observations

Checks used HTTPX/WebSocket clients in an interactive Python console. Every received server message was validated with the real public protocol validator. Clients kept five-second heartbeats; no credentials were printed or recorded.

| Check | Result |
|---|---|
| Explicit migration before coordinator startup | Passed; SQL reported `0001_registration` |
| REST create/join, socket hello and complete welcome | Passed with real SQL, two rooms, four phones in each, and a second screen in room A |
| Room ownership/isolation | Passed; each worker reported one room; room A connections shared one simulation, room B remained independent |
| Authentication and authority | Passed; invalid/cross-room tokens closed 4401; wrong Origin and query-token handshakes rejected 403; private worker endpoint rejected missing credentials; phone match.start returned FORBIDDEN |
| Readiness and host start | Passed; both rooms reached countdown and active through routed commands/events |
| Legs/Arms routing | Passed; Legs moved its assigned character, Arms aim changed that team's direction, Arms phone sending Legs returned WRONG_ROLE |
| Ordered Arms edges and state | Passed; press acquired, cancel dropped, press reacquired, release inside the zone returned NO_THROW_ZONE, retreat with fresh aim followed by release produced a flying-ball snapshot |
| Error targeting | Passed; NO_THROW_ZONE reached the responsible Arms controller with the release sequence reference, not the screen |
| Snapshot/transition consistency | Passed; screens agreed at matching snapshot ticks; observed state epochs/ticks never regressed through welcome, countdown, active and snapshots |
| Worker A SIGKILL during play | Passed; all six affected sockets received room.closed and closed 1012; worker B continued active snapshots |
| Durable worker-loss handling | Passed; room A retained closed_reason worker_lost; all six member records were retained and revoked |
| Restart failed worker | Passed; prior room token closed 4404 and REST join returned 404; lost game was not reconstructed |
| Coordinator restart | Passed; room B history retained with server_restart; its five member records retained and revoked; old token closed 4404; health counted zero open runtime rooms |
| Fresh room after restart | Passed; REST registration and lobby welcome worked |

The SQL observations after coordinator restart were:

| Retained room | closed_reason | Members | Revoked |
|---|---|---:|---:|
| A | worker_lost | 6 | 6 |
| B | server_restart | 5 | 5 |

The SQL query inspected closure flags/reasons and member counts, never tokens or token hashes.

## Queue and slow-client observations

Separate direct runtime probes exercised the same GameRoom/Peer/WorkerRoom implementation used by the containers. These deliberately blocked a socket sender or filled a command queue; they were not internet/browser saturation measurements.

- A blocked peer did not stop the room runner: tick advanced by more than five over 200 ms and a healthy peer still received messages.
- Sending 1,000 pending snapshots retained only the latest. A reliable message discarded an older pending snapshot; a newer snapshot remained behind the reliable message.
- Reliable queue stayed bounded at 32; overflow closed the slow peer with 4400.
- Worker command queue accepted 128 entries in FIFO order. Entry 129 raised SERVER_BUSY/503 and cancelled the channel task. The networked worker/channel-loss check separately verified room closure behavior.
- Backend compileall, `uv lock --check --offline`, root Compose configuration validation and `git diff --check` passed.

## Failure/restart commands and cleanup

The destructive probes targeted only the isolated project:

```sh
docker compose -p dodgewuh-section1 -f docs/demo/section1-local.compose.yaml kill -s SIGKILL game-worker
docker compose -p dodgewuh-section1 -f docs/demo/section1-local.compose.yaml up -d --wait game-worker
docker compose -p dodgewuh-section1 -f docs/demo/section1-local.compose.yaml restart coordinator
```

After recording results, the isolated containers/network were removed with `down` without `-v`; its database volume was retained. The original development project was not restarted. No registry push, AWS/DNS changes, production migration or image rollback was performed.

Remaining work is tracked in sections 2–7 of [todo.md](../../todo.md), including reservation/TTL cleanup, live phase persistence, allocation/result history, deployment and real-device acceptance. Richard's scoring/round/role lifecycle was pending in the verified source. His subsequently merged implementation requires its own integration verification; this record does not establish full-match completion.
