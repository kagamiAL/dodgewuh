# Alan — second integration milestone checklist

Working target: the next gate after the first phone-to-screen movement slice is **two real phones cooperating to pick up and throw, through the coordinator and game worker, on public HTTPS/WSS**. This follows the H4 → H6 sequence in [the roadmap](plans/05-development-roadmap.md). The hours are historical targets, not current deadlines. Confirm the integration slot and exact gate with Ryan; do not interpret this checklist as proof that anything has been deployed.

This is Alan's preparation list, followed by the checks that require the team. Richard owns physics/lifecycle; Ryan owns frontend/session/rendering; Morteza and Tysen own physical controllers/sensors. Keep their implementation work with them. Use the existing contracts and manual checks; do not add automated tests, test harnesses or test-only dependencies.

## 1. Finish and verify the coordinator → worker path

Current status: **section 1 complete for local backend verification**, routing source committed as `6b02f9cae29a808650b06190352a255ec5c486e4`. The isolated Compose stack passed checks against real PostgreSQL, two workers and the public-facing REST/WebSocket routes. Clients were synthetic; browser/physical-device checks and public HTTPS/WSS deployment remain in later sections. See the [manual verification record](docs/demo/section1-worker-routing.md). The routing commit was subsequently replayed as `0a09b90` over Richard's newer simulation; that simulation and concurrent lifecycle changes need separate verification.

- [x] Implement one runtime worker allocation/channel per room and move the authoritative simulation onto the worker.
- [x] Implement shared-secret authentication on the private worker endpoint; forward authenticated membership facts and commands without forwarding public bearer tokens.
- [x] Locally verify shared room ownership, independent rooms, welcome delivery, readiness/start transitions, snapshots and rejection of unauthorized host commands using simulated clients.
- [x] Locally verify rejected unauthenticated worker connections, isolated channel-loss closure, worker shutdown handling and failed-room allocation blocking. The initial probe used a SQL stand-in; the follow-up Compose check verified actual PostgreSQL closure/revocation.
- [x] Review and commit the routing changes; record the exact SHA used for verification (`6b02f9cae29a808650b06190352a255ec5c486e4`). Keep one coordinator process and one process per worker.
- [x] Build and start PostgreSQL, worker and coordinator with Compose; run Alembic explicitly before coordinator startup. Verify both health endpoints and their build identifiers.
- [x] Create a room through REST, register screens/phones, authenticate through the public WebSocket route, and receive a consistent welcome baseline.
- [x] Repeat the verified local ownership/isolation checks through REST registration and the public WebSocket route with real PostgreSQL. Confirm authenticated identity and token handling across that complete path.
- [x] Verify normalized Legs and Arms commands, ordered press/release/cancel edges, snapshots, errors and transition events travel through the worker. Check bounded queues, latest-snapshot delivery and transition ordering; slow clients must not stall the simulation. Passed routed input/event checks plus direct runtime probes with a deliberately blocked sender and queue saturation; not a browser/network load benchmark.
- [x] Kill/restart a worker during play. Observe room.closed/socket closure, persisted worker_lost closure and revoked memberships in PostgreSQL; old tokens must not recreate the lost room. Verify an unaffected worker/room continues if another worker is configured.
- [x] Restart the coordinator and confirm former runtime memberships are invalidated while saved records remain. Do not attempt mid-match resume.

## 2. Close backend contract and room-lifecycle gaps

Use [plan 03](plans/03-api-contracts.md) for exact behavior. Several of these policies are not implemented completely in the current tree; existing disconnect-to-lobby handling alone does not satisfy them.

- [ ] Implement authenticated DELETE /api/rooms/{room_code}/members/me. Revoke membership, release its slot and notify live worker peers. Host leave closes the room; phone leave during play safely aborts to lobby.
- [ ] Implement the 30-second unconnected-registration/disconnected-lobby reservation expiry and host-expiry closure. Coordinate SQL slot release with worker assignment/status removal; preserve occupied assignments and fill vacant team/role pairs in canonical order.
- [ ] Implement five-minute empty-room cleanup alongside the existing 30-minute idle-lobby and four-hour hard expiry. Close live sockets/channels and cancel worker runners/sender tasks when a room expires. The current worker relay retains empty channels until shutdown, so SQL expiry alone is insufficient.
- [ ] Synchronize the live phase into coordinator registration policy so a new phone cannot join an active match; screens may join in any phase. Keep blocking SQL outside the 60 Hz tick and serialize phase changes with registration decisions.
- [ ] Manually verify four-phone/four-screen caps, host-only controls, wrong-role rejection, malformed/oversized/rate-limited input, stale epoch/assignment/sequence handling and reconnect with a fresh input sequence.
- [ ] Verify ready=false or required-device loss during play aborts safely, stops movement/Hold and clears readiness. A replacement socket must not be controlled or detached by the superseded socket. Reconnection restores identity but requires fresh calibration/readiness/start.
- [ ] Verify late-screen welcome and phase/role bundles are consistent and never regress epoch/assignment version. Retain camera.claim authorization and current camera-driven Legs behavior.
- [ ] Confirm protocol models, generated TypeScript types/validators, JSON Schema and shared fixtures agree. If a wire change is necessary, coordinate it and update all representations together.

## 3. Verify Richard's physics through the real routing path

The current simulation includes pickup, ownership, cancellation, flight, respawn and hit results. It freezes on a decided hit without advancing score/round; Richard's lifecycle tasks remain pending.

- [ ] Run Richard's existing manual diagnostics (`PYTHONPATH=backend backend/.venv/bin/python -m simulation.synthetic`) and validate the committed snapshot fixtures against the public protocol models.
- [ ] Through coordinator → worker, verify movement, nearest-ball pickup, held ownership, release strength/aim, flight, collision/hit result, wall/expiry respawn and cancellation.
- [ ] Confirm NO_THROW_ZONE reaches only the responsible controller with the correct ref_seq, without producing a throw. Compare snapshots/results to Richard's fixtures.
- [ ] Verify press and release received in one tick retain order; reset/disconnect cancels held controls; invalid/stale commands cannot change gameplay.
- [ ] Give Richard concrete adapter/fixture discrepancies with the SHA and sanitized messages. Do not patch simulation rules in Alan's adapter.

## 4. Complete the persistence required for the implemented slice

[Plan 11](plans/11-sql-persistence.md) requires more than room/member registration. Current SQL models only cover those two record types; worker allocation is runtime-only.

- [ ] Add explicit migrations/repositories for assignment and worker-allocation metadata now that allocation exists. Persist initial assignments and subsequent authoritative role changes, without treating SQL as gameplay authority.
- [ ] Define and implement coordinator-owned match lifecycle/result persistence with an authenticated worker reporting interface. Serialize writes outside the simulation tick; use stable match identity and uniqueness/idempotency so duplicate callbacks cannot award or save results twice.
- [ ] Record interruption/abort on worker/coordinator loss and preserve history while invalidating old sessions. Never persist raw sensor samples, live ball trajectories, sockets or process-monotonic expiry values.
- [ ] Coordinate actual completed-result/role-switch emission with Richard. If his lifecycle is unavailable at the second integration, explicitly record that dependency and the unverified result path; do not invent completion events or claim full-match persistence passed.
- [ ] Apply migrations to a disposable/local PostgreSQL database; verify restart retention, revoked-token rejection and duplicate-report handling where implemented. Check migration compatibility before deploying against retained data.

## 5. Prepare and deploy the public integration environment

Public hosting is part of the planned second integration target. Terraform/Compose files existing in Git do not establish a deployed environment.

- [ ] Verify AWS/account/region, registry and Porkbun domain access. Run Terraform fmt, validate and plan; review the saved plan before the approved apply. Keep state/plans/secrets outside Git.
- [ ] Provision or verify the two EC2 hosts, coordinator Elastic IP, worker private address and encrypted PostgreSQL disk. Check cloud-init, Docker/Compose, Session Manager and the mounted data volume before starting PostgreSQL.
- [ ] Build/publish an immutable backend image and record its tag/digest and BUILD_SHA. Arrange registry access on both hosts. Use the same release on coordinator and worker.
- [ ] Obtain Ryan's matching frontend build and serve it through Caddy with SPA route fallback, while proxying /api and /ws to the coordinator. Replace the current placeholder root response. Verify required browser assets load in production.
- [x] Add GAME_WORKER_SECRET to local and production Compose configuration and the local environment example; document matching secrets and private worker URLs. Actual production secret provisioning remains pending.
- [ ] Configure production environment: BACKEND_IMAGE, BUILD_SHA, DOMAIN, private GAME_WORKER_URL, WORKER_PRIVATE_IP, protected PostgreSQL password file and the same strong GAME_WORKER_SECRET on both backend services. Never use development secrets in production.
- [ ] Set the exact public Origin allowlist; disable wildcard DEV_ORIGINS in production. Verify wrong-Origin and unauthenticated public/internal connections are rejected. Configure trusted proxy handling so REST rate limits use the intended client address.
- [ ] Keep PostgreSQL unpublished and worker port accessible only from the coordinator. Preserve unrelated DNS records; point dodgewuh.fit to the coordinator and verify A/AAAA resolution and Caddy certificate issuance.
- [ ] Start PostgreSQL, run Alembic upgrade head once for the release, then start the worker and coordinator/Caddy stacks. Verify schema revision, readiness, build SHA, frontend HTTPS and browser WSS upgrade/state flow.
- [ ] Exercise public room creation/join and input → worker → snapshot on an actual browser/device. Observe WSS state flow for ten minutes, including a cellular connection if available. Record any synthetic participants explicitly.
- [ ] Record deploy/start/stop/log commands, the previous runnable release and rollback procedure. Back up retained SQL data off-host and verify a disposable restore before relying on it; image rollback does not roll back schema. Keep destructive cleanup separate from deployment.

## 6. Prepare the handoff before the integration session

- [x] Run backend compileall, the local worker relay runtime check, dependency lock consistency checking and local Compose configuration validation on the current working tree. These passed; routing source is committed as `6b02f9c`, with follow-up local Compose/SQL verification recorded. Nothing is deployed publicly.
- [x] Update root/backend READMEs for worker routing, authentication, failure behavior and the deployment configuration requirement.
- [ ] Run relevant backend compile/runtime validation, frontend typecheck/build and Compose configuration checks on the chosen SHA. Fix failures or document the exact blocker; do not substitute a build for gameplay evidence.
- [ ] Finish updating stale status notes in contracts/infra READMEs and plans/agents/alan-progress.md; review root/backend READMEs for remaining gaps. Distinguish implemented code, local verification, deployed verification and remaining dependencies; remove obsolete IN_PROCESS_SIMULATION instructions.
- [ ] Save a manual smoke record under docs/demo with SHA, UTC timestamp, image digest, migration revision, startup commands, public HTTPS/WSS origin, observed message/state flow, disconnect/worker-loss results and rollback observations. Never include tokens, passwords or private keys.
- [ ] Give Ryan and the controller owners the origin, create/join examples, Transport usage, fixture paths, role/epoch/sequence requirements and room-loss/reconnect behavior. Agree on the matching frontend/backend release.
- [ ] Confirm Richard's supplied simulation revision, Morteza's Arms readiness and Tysen's Legs/sensor readiness. List missing pieces and their owner before the session; use synthetic inputs only for clearly labelled backend preparation.

## 7. At the second integration — checks requiring the team

These are joint acceptance checks, not work Alan must falsely certify alone before meeting everyone.

- [ ] Clean browser opens the public site; screen creates a room; two real phones join, grant required permissions, calibrate and ready. Any extra required seats filled synthetically must be declared; that does not pass four-human acceptance.
- [ ] Legs moves the correct authoritative character; Arms cooperates to pick up, aim and release; screen shows worker state. Verify cancellation cannot throw and NO_THROW_ZONE feedback reaches the Arms controller.
- [ ] Disconnect/background a controller and verify safe cancellation/reset, clear readiness and understandable reconnect behavior. Verify a late/second screen gets the correct baseline.
- [ ] Ryan records observations and owners for defects. Report the second gate as blocked if physical Arms, trusted HTTPS/WSS or real routing is unavailable; a synthetic throw alone is not a passed physical-control gate.

## Later full-match acceptance — retain as dependencies, not second-gate prerequisites

Richard must supply score-once, timeout draw, round transitions, role swapping, first-to-three and rematch lifecycle. Once available, Alan integrates/persists those events and verifies idempotency and restart/abort history. With Ryan, Morteza and Tysen, run the full public four-real-phone match, recalibration after role swaps, two-screen agreement, cancellation/disconnect and rollback rehearsal described in [plan 06](plans/06-integration-and-testing.md). Record a separate passed/failed result; the second gate is not full-MVP completion.

Sources: [backend workstream](plans/teams/backend-alan.md), [Alan brief](plans/agents/alan.md), [contracts](plans/03-api-contracts.md), [roadmap](plans/05-development-roadmap.md), [acceptance](plans/06-integration-and-testing.md), [deployment runbook](plans/08-deployment-runbook.md), [persistence amendment](plans/11-sql-persistence.md), [backend operations](backend/README.md), [infrastructure operations](infra/README.md).
