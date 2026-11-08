# Section 3 — Richard's physics through coordinator and worker

Passed local manual backend verification on 2026-11-08, approximately 01:07–01:11 UTC (2026-11-07 in Edmonton). All controller clients were synthetic. Public HTTPS/WSS, browsers, sensors, physical phones, full-match routing and result persistence were outside this check.

## Verified source and environment

HEAD was `a2d609352103bb216ad5f0e8bb3cd52c098f774d`, containing Richard's task 7 implementation `4062ebb` via merge `6d610fa`. The workspace already contained concurrent room-lifecycle edits in eight backend files. These were included in the frozen image, preserved without modification by this task, and must not be confused with clean HEAD verification.

- Frozen local image: `dodgewuh-section3:local`, image ID `sha256:6516d47194f76010058f619d082b221832df52534307e023ac73beb4b04db856` (local image ID, no registry digest).
- BUILD_SHA on all services: `a2d6093-working-50c2c9933d8f`.
- Backend source fingerprint: `50c2c9933d8fe0a21049250dd337bb1c73a9d0467d851fa882ed56f97d7c2a26`. Computed by SHA-256 over each existing `git ls-files backend` path in Git's order: path bytes, NUL, file bytes. This pins the dirty source independently of HEAD; future edits require rebuilding and rechecking.
- Simulation engine SHA-256: `fc59226ea9120ea15dfb8888edbf2fd334f64aba67ab7d5afdff6c4da0b168af`.
- Game adapter SHA-256: `7c43529396f1929ed6b6eae91cc338404a345659153799585397a0d0ffe9dd7b`.
- Python 3.12, PostgreSQL 17.11, explicit Alembic upgrade to `0001_registration` before coordinator startup.
- Separate Compose project `dodgewuh-section3`, fresh database volume, one coordinator and two workers, one Uvicorn process each, no reload or source mounts. Existing development containers were left running unchanged.
- Public-facing local REST/WS endpoint: `http://127.0.0.1:19000`, `ws://127.0.0.1:19000/ws/rooms/{code}`; Origin `http://localhost:5173`, wildcard origins disabled. Worker endpoints were local ports 19001/19002; coordinator used authenticated private channels.

The [retained Compose configuration](section3-local.compose.yaml) contains no secrets. Supply fresh isolated `SECTION3_WORKER_SECRET` and `SECTION3_POSTGRES_PASSWORD` through an external environment file. Startup used:

```sh
docker compose --env-file /tmp/section3.env -p dodgewuh-section3 -f docs/demo/section3-local.compose.yaml build coordinator
docker compose --env-file /tmp/section3.env -p dodgewuh-section3 -f docs/demo/section3-local.compose.yaml up -d --wait postgres game-worker game-worker-b
docker compose --env-file /tmp/section3.env -p dodgewuh-section3 -f docs/demo/section3-local.compose.yaml run --rm --no-deps coordinator /app/.venv/bin/alembic upgrade head
docker compose --env-file /tmp/section3.env -p dodgewuh-section3 -f docs/demo/section3-local.compose.yaml up -d --wait coordinator
```

Rebuilding later changes the verified image; BUILD_SHA here is a verification label, not a guarantee that later source matches. Do not overwrite retained database credentials by supplying a new password to an old volume.

## Observations

HTTPX/WebSocket clients created a room through REST, registered one host screen and four phones in canonical seat order, authenticated with session.hello, sent periodic heartbeats, reported calibration/readiness and started through the host. Every received server envelope was validated with `app.protocol.server_messages`. Gameplay setup used real movement commands and observed snapshots, without teleporting or changing worker simulation state.

| Check | Observed |
|---|---|
| Existing diagnostic runner | 262/262 observations matched under local Python 3.12 and inside the frozen worker-compatible image; full synthetic match/rematch included |
| Committed fixtures | All eight validate against public server protocol models; regeneration into a temporary directory is JSON-identical to every committed fixture |
| Movement and nearest pickup | Team 1 moved from spawn to approximately (-2,-1.4); press picked nearest b1 at (-2,-0.6), mode held, owner_team 1 |
| Held ownership and tracking | Continuous aim updates preserved Hold while Legs retreated; held ball followed its character |
| NO_THROW_ZONE targeting | Release within the zone produced error only on the responsible Arms socket, ref_seq 18; b1 grounded, no flying-ball snapshot on screen |
| Cancellation | Cancel grounded the held ball without throwing |
| Ordered edges over routing | Back-to-back press/release inside zone produced the release's NO_THROW_ZONE response; edges were retained |
| Release strength/aim | Retreat to approximately (-2,-3), release strength .5 with aim (0,1) yielded flying b1 velocity (0,11), matching 8 + 6 × .5 |
| Collision/result | Opponent moved to approximately (-2,4); real throw produced round_end with hit, winner 1, hit_ball_id b1, victim_team 2; score 1–0 |
| Round lifecycle | Result display advanced to role_switch; assignment_version became 5 and roles swapped, rather than freezing on the decided hit |
| Wall respawn | Aim (sqrt(.96),.2), strength 1 yielded flight, court exit, respawning, then ground at b1's original (-2,-.6) |
| Flight expiry | Shooter near (-2,-8), opponent moved to (4,6), strength 0 and aim (0,1): flight expired inside court after two seconds, then one-second respawn to ground; phase remained active |
| Host reset during Hold | Returned to lobby with all balls grounded |
| Arms disconnect during Hold | Remaining host observed lobby with all balls grounded; adapter abort cancelled held controls |
| Routed command defense | Separate room: duplicate release -> OLD_SEQ, stale-epoch release -> STALE_EPOCH, Arms member sending Legs -> WRONG_ROLE; b1 stayed held by team 1 after each rejection |

The first long throw attempt lost Hold because the diagnostic client stopped sending Arms updates while moving. This was expected 250 ms stale-input cancellation, not an adapter defect. Repeating with 10 Hz aim updates passed the complete route. No gameplay code was changed to accommodate the probe.

Network delivery alone cannot prove that two messages arrived within exactly one fixed step. A separate manual direct `GameRoom.handle` probe stopped the runner, used Richard's active diagnostic setup with b1 in pickup range, submitted press then release through `decode_client`, and observed two pending commands while tick remained 180. One `step()` produced flying b1 at speed 11. Duplicate seq and stale epoch were also rejected with an unchanged snapshot. This direct probe supplements the routed edge check; its controlled geometry is not claimed as REST/WS evidence.

## Fixture comparison and handoff to Richard

The routed held/flight/result/reset states agreed with the fixture invariants: owner only when held, shooter only when flying, grounded zero velocity, result reason/winner/victim/ball fields, and score/phase behavior. Routed member IDs, tick, epoch, positions and assignment versions naturally differ from Richard's deterministic fixture scenarios; whole-message equality is only claimed for regenerated fixture files, not independently timed network snapshots.

Sanitized routed hit payload:

```json
{"reason":"hit","winner":1,"hit_ball_id":"b1","victim_team":2}
```

Sanitized targeted error fields: `code=NO_THROW_ZONE`, `ref_seq=18`; no other socket received that error. No adapter/fixture discrepancy requiring Richard to change a rule was found. This record is the prepared handoff; no external message was sent.

At the time of the initial frozen-image check, Richard's HANDOFF.md and synthetic runner reported task 8's readiness/device-loss guard inside `Simulation.step()` as absent. The uncommitted engine edit in the verified image changes assignment removal, not that guard. The adapter currently calls `control('abort')` itself; that path passed here. Do not interpret the user's delivery update, the passing task 7 diagnostics, or the routed disconnect success as proof of simulation-owned task 8 completion. Ownership/decision-point cleanup remains a separate coordination item.

No simulation rules, protocol definitions or fixtures were modified. No automated tests, permanent harness or dependencies were added. Backend compileall passed. Section 4 persistence and later public/device acceptance remain separate work.

After verification, only the isolated section 3 containers/network were stopped with Compose `down` without `-v`; its database volume was retained. No production/AWS/DNS changes were made.

## Follow-up — delivered simulation-owned guard

The pending-task-8 note above is historical and superseded. Richard delivered `ccbc156` (merged as `aafcb11`). At follow-up HEAD `8f2b17eba31bde1aeff6b32ca1fbf77fc1db5c49`, the engine, handoff and diagnostic runner all include the simulation-owned guard.

Re-ran `PYTHONPATH=backend backend/.venv/bin/python -m simulation.synthetic` under Python 3.12: **413/413 observations match**. The added diagnostics cover required-device loss in every non-lobby phase, readiness revocation in countdown/active, waiting in role_switch, no repeated guard abort in lobby, held-control reset, stale input after abort, and device loss taking precedence over a simultaneous hit. All eight committed fixtures also validate against the public protocol models.

No engine mechanic remains pending from Richard's tasks 1–8. This follow-up verifies the delivered simulation directly; it does not relabel the earlier frozen image as containing task 8 or claim a new routed/physical-device acceptance run. The adapter still contains explicit abort calls; the earlier routed cancellation checks exercised those calls.
