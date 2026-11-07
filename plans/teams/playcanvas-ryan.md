# Vue and PlayCanvas frontend — Ryan

Deliver the browser presentation and shared UI for a playable MVP. This is a separate workstream from Richard's authoritative simulation. Ryan renders server state, integrates the phone components and coordinates end-to-end merges.

Read [architecture](../01-architecture.md), [rules](../02-game-specification.md), [contracts](../03-api-contracts.md) and [ownership](../04-repository-structure.md) before implementation. Keep this a working MVP: implement the playable loop before polish.

## Scope and ownership

Own frontend files except Alan's net/generated/net tests, Morteza's Arms files/tests and Tysen's Legs/sensors/playground files/tests, as enumerated in [04](../04-repository-structure.md). Also own tests/e2e/** and docs/demo/**. Own frontend dependency manifests, app/router/session store, screen, lobby, HUD, PhoneShell and mock-state rendering.

Do not implement movement physics, pickup, hit detection, scoring or authoritative timers. Use primitive geometry; no animation assets or visual effects are required. Alan owns transport and generated wire types; Richard owns the simulation and rules.

## Rendering specification

One canvas-owned Application, root entities Arena, Characters, Balls, Camera, Lights. Arena consists of floor, boundaries, centre line and translucent no-throw strips derived from [02]. Team colours and labels match phones. Character entities keyed by team; ball entities keyed by ball_id, with mode controlling visibility/attachment display. Held pose derives from state only; a renderer must not infer pickup from proximity. Flying balls use server position with optional visual spin; collision never runs here. Camera elevated from negative z with all court visible; resize preserves view and readable HUD.

Vue Screen mounts/unmounts engine cleanly; HUD displays server phase/score/remaining_ms and connection status. Server phase decides countdown, results, switch, winner and lobby. Both screens run exactly this same component and snapshot path. Start/reset/rematch controls appear only for original host, enforced again server-side. Late screen uses welcome.state; no synchronization handshake beyond the common protocol.

PhoneShell is Ryan's shared UI integration: current assignment selects Arms or Legs Vue component using [03] props; components emit calibrated(boolean) and availability(Permission); explicit Ready tap sends ready=true, and loss of calibration/availability immediately sends ready=false per [03]. On welcome, lobby reset or role change stop/unmount old role, cancel any local pointer state, show new role and recalibrate. Do not duplicate sensor listeners or allow PhoneShell to invent commands. Permission/granted/calibrated state should be visible to host in lobby.

## Implementation sequence

1. Bootstrap Vue/Vite/TypeScript and mount a primitive PlayCanvas scene using a complete validated reset snapshot.
2. Feed mock snapshots through the final message handler; cover state changes, resets and stale data without implementing a local game simulation.
3. Implement create/join, device selection, lobby and session store using Alan's Transport. At H4, replace mock source with live snapshots and display real phone-driven movement.
4. Add aim, possession and no-throw cues, then score/timer/phase overlays. Render latest snapshots first; add simple interpolation once movement works.
5. Mount Morteza's and Tysen's components through PhoneShell. Coordinate calibration/Ready and component replacement after role changes.
6. Add host start/reset/rematch, winner and clear connection-loss UI. Join a second screen using the identical render path.
7. Coordinate the full four-phone cloud match, H18 freeze and demo recording. Fix blocked acceptance cases before cosmetic work.

## Mocks and handoffs

mockSource and live Transport deliver the same validated ServerMessage objects to one handler. Consume Richard's fixtures through Alan; request missing state examples rather than inventing fields. See [Richard's plan](simulation-richard.md) for the producer boundary. No keyboard-driven local simulation in the renderer.

Give motion owners exact component props/emits, route imports and readiness behavior. Give Alan reproducible transport failures without tokens. Report fixture gaps to Richard through Alan's schema ownership. Keep small working merges and record the integrated release SHA.

## Tests and acceptance

- [ ] Vue mount/unmount cleans up engine, resize and render subscriptions.
- [ ] Screens display server positions, possession, score and phase without determining outcomes.
- [ ] Reset/epoch changes clear interpolation; stale streams freeze with visible status.
- [ ] Late and secondary screens display identical tick-matched state.
- [ ] PhoneShell swaps roles and requires fresh calibration/readiness.
- [ ] A four-phone hosted match reaches winner/rematch with usable primitive visuals.

Run frontend typecheck, focused UI/render tests and production build. Definition of done: mock and live sources share handlers, Ryan-owned acceptance rows in [06](../06-integration-and-testing.md) pass, and the real-device demonstration is recorded with its SHA and limitations. Use [Ryan's coding-agent brief](../agents/ryan.md) for execution.
