# Integration and acceptance

> This is the original acceptance plan, not a test report. Some listed features
> have since been implemented, but no acceptance item should be treated as passed
> from this document. Current limitations are summarized in the repository and
> contract READMEs. Arms phone UI and authenticated worker routing are implemented;
> this historical checklist is not a current verification record.

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

Test behavior that can break the playable loop. Use manual gameplay checks and real-device observation; do not create automated tests. Code compiling is necessary but does not prove a usable game. Ryan coordinates each integration gate; each owner fixes their files.

## Production-compatible mocks

| Owner | Harness | Replacement gate |
|---|---|---|
| Richard | Pure Simulation with fake member IDs, exact LegsCommand/ArmsCommand DTOs and supplied tick/time; output full State fixture | H2 Alan uses real Simulation; synthetic runner stays manual diagnostic tool |
| Ryan | SnapshotSource delivers validated ServerMessage fixtures at 20 Hz; same handler as Transport; include phase reset | H4 replace source with subscribed real transport, no renderer rewrite |
| Morteza | Same Arms component + recording MockTransport, real/replayed SensorService | H4 join actual room, then H6 real two-phone throw |
| Tysen | Same SensorService/Legs component in playground; trace raw, neutral and normalized vectors | H4 actual WSS; keep playground for tuning |
| Alan | MockSimulation implements exact [03](03-api-contracts.md) seam; fixtures and synthetic WS clients | H2 switch runner factory to Richard implementation; no mock production path |

Alan owns canonical valid/invalid fixtures. Richard contributes snapshots through Alan; Ryan and controller owners consume them rather than duplicating types. Schema fixtures cover unknown event/field, wrong version, null/nonfinite vector, bool-as-number, missing nullable fields and unknown phase enum. Python and TS validators must agree on these. Wrong role, valid-but-disallowed phase, stale epoch, duplicate seq and unauthorized host actions are stateful adapter/simulation scenarios, not schema-invalid JSON. Keep one happy-path fixture per event plus these risk-bearing cases; do not build a second validation framework.

Before the first multiplayer merge, manually check the amended seams: ready=false during active aborts; pre-reset ready=true is rejected; reset retaining assignments still clears PhoneShell calibration; one sensor stream cannot refresh another; reconnect seq=1 reaches simulation; a superseded socket cannot disconnect its replacement; press+release in one tick remains ordered; winning-round transition bundles never regress epoch. These protect the playable loop, not optional polish.

## Manual verification scenarios

Richard: deterministic movement bounds and stale stop; all four ball spawns; nearest/tied pickup; release outside/inside zone boundary; cancellation; swept collision at maximum speed; simultaneous hit draw; exact 3600-tick timeout; score increments once; reset and best-of-3; every-round role swap; old input epoch rejected.

Alan: REST creation/code uniqueness, four phone/four screen caps, no phone join mid-match, token/Origin checks, welcome and full snapshots, synthetic Legs routed only to its member, no client score authority, ready/start gates, bounded send queue, disconnect→lobby reset and dead-member reservation expiry, in-memory restart behavior. Observe TTL expiry manually and record the configured durations.

Ryan: scene mounts/unmounts without duplicate loops, interpolation skips round/epoch boundaries, discrete score/possession snap, late viewer baseline, stale overlay, PhoneShell switches components and clears calibration, permission status displayed in lobby. Compare both screens at matching snapshot ticks, not arbitrary screenshot wall times.

Motion: record 10 neutral periods (no drift), 10 moves each direction, 20 gesture/releases, 10 cancel paths (pointercancel, lost capture, visibility change, disconnected transport). Target ≥9/10 intended direction trials and ≥18/20 deliberate throws, zero cancel throws. Numbers are go/no-go targets, not measured results. Tysen records model, OS, browser, HTTPS origin, permission behavior, usable fields and sample rate. At least one actual iPhone Safari test in H1; four real phones in H8, including available Android only if used in demo.

## MVP traceability matrix

Rows cover all 24 master acceptance requirements; combined rows exercise related observable outcomes. Tests are planned, not claimed executed.

| Master criteria | Owner | Acceptance procedure |
|---|---|---|
| 1–3 public site/create/code | Ryan + Alan | Clean browser loads HTTPS, create returns usable code visible on page |
| 4 screen joins | Ryan + Alan | Host screen is registered; second laptop joins by code |
| 5–6 four phones/assignments | Alan + Ryan | Join four physical phones; exactly one Arms and Legs each team; fifth rejected |
| 7 sensor permission | Tysen + Morteza | Each grants relevant APIs from tap; denial blocks Ready with recovery guidance |
| 8 start | Alan + Richard | Host start blocked with three phones or unready phone; succeeds with four and screen |
| 9–10 cooperation/physical Legs | Tysen + Richard + Ryan | Arms alone cannot move; torso lean on Legs moves correct team in four directions |
| 11 pickup via Hold | Morteza + Richard | Legs approaches, Arms holds, nearest ball becomes held; away from ball no pickup |
| 12 physical aim/throw | Morteza + Richard | Phone lean changes aim; small safe swing + release launches, neutral release cancels |
| 13 four balls | Richard + Ryan | Initial and every reset scene/state show four at specified middle positions |
| 14 no-throw zone | Richard + Ryan | Inside zone release does not launch; incoming valid ball still hits |
| 15 hit/point/end | Richard + Ryan | Opponent hit produces one point immediately and phase change on all clients |
| 16 timeout | Richard | 60 seconds without hit produces draw/no score; one live 60-second observation |
| 17 role switch | Richard + Ryan + both motion owners | After hit AND draw, each phone changes role and requires new calibration/Ready |
| 18 next round reset | Richard | New countdown has reset positions, four balls, full time; prior commands rejected |
| 19 multiple screens | Ryan + Alan | Same room on two screens agrees tick-matched state for 5 minutes; no local outcomes |
| 20 match winner | Richard + Ryan | Play to two points or the end of round three; winner/score agree; rematch returns lobby |
| 21–22 cloud HTTPS/WSS | Alan | Public domain valid cert, WSS 101 and full State flow for 10 minutes from phone cellular network |
| 23 four real phones | All, Ryan records | Complete full match with four devices, no synthetic participants |
| 24 no native install | Ryan + Tysen | Clean mobile browser joins using only URL/code and sensor prompts |

## Full end-to-end script

Deploy known SHA, create room, join second screen and four phones, grant/calibrate/ready, start. Move both teams, hold-pickup, retreat outside zone, aim and swing/release. Observe hit, score, swap, recalibrate and next round. Exercise one timeout draw. Complete best-of-3 and rematch. Disconnect a phone while holding: ball must not fly, match resets to lobby and readiness clears. Reconnect with same token within reservation window, ready and restart. Open a late screen and compare baseline. Repeat on actual demo network. Save results in docs/demo with SHA, device list, timestamp and failures, never credentials.

## Troubleshooting and readiness

No sensor data: confirm secure context, foreground, user-gesture permission and finite API fields before changing math. Wrong direction: verify portrait orientation, neutral calibration, team world mapping. No movement: inspect epoch/role/seq rejection, then adapter receipt, then simulation position, then snapshot tick, then renderer. No throw: inspect local gesture window, Hold pointer state, server possession and zone. Stale screen: inspect WS close/logs, send queues, origin and proxy path. Split rooms: confirm one Uvicorn worker. Public TLS failure: check DNS A/AAAA, ports and Caddy logs using [08](08-deployment-runbook.md).

Demo ready only when public clean-browser flow, four actual phones, role switch, full match, cancellation and two-screen tests pass on pinned release. Have a charged backup phone, stable network, room creation instructions, recorded run, previous deploy artifact and clear known limitations. One final focused smoke after release; avoid repeated broad tests without a new failure or change.
