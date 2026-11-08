# Gameplay specification — rules authority

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

> **Rules amendment — ballistic ball flight (Richard, 2026-11-07).** Flight was previously "straight 2D"
> with y as a purely visual height. Balls now fall under gravity and come to rest where they land. Three
> things this deliberately does **not** change: the throw itself (same aim, same offset, same speed formula —
> there is still no vertical-aim input), the collision test (still the flat 2D swept circle, because a
> horizontally released ball never rises above a character's height), and bounce (still none). What changes:
> balls arc downward, they stop where they touch down instead of flying on, and the 2 second lifetime is no
> longer reached in normal play. `Ball.height` is added to published state for rendering only; it is never a
> gameplay input. The matching additive field has been applied through [03](03-api-contracts.md), the Pydantic
> and Zod models, the shared fixtures and the renderer, because strict validation on both sides meant a
> simulation-only change would have rejected every snapshot. **Alan owns 03 and the generated models: please
> re-approve those edits.** The per-file list is in `backend/simulation/HANDOFF.md`.
> Gravity is 3.4 m/s², below Earth's 9.81 by design: at 9.81 a fixed-strength throw carries only 5.44 m, so a
> defender standing at their own back wall is literally unhittable and every round times out — the long-draw
> risk in [07](07-risks-and-fallbacks.md). 3.5 keeps the whole court reachable while still visibly arcing.

This file is the sole source of gameplay rules and constants. Values below are explicit MVP engineering decisions, not validated sensor measurements. Network representations live in [03](03-api-contracts.md). Richard owns their implementation.

The original team plans describe torso lean on the phone; the merged Legs
controller evolved to pocketed jog-in-place with facing direction, and screens
can also drive Legs by locally processing camera poses. These are control input
methods; the movement rules and normalized `input.legs` contract below remain the
authority. Actual phone/browser compatibility still requires device checks.

## Coordinates and constants

| Constant | Value |
|---|---|
| Simulation | Fixed 60 steps/s; dt = 1/60 s |
| Court | x ∈ [-6,6], z ∈ [-9,9] metres; y is height, simulated for ball flight but never a collision input |
| Team halves | Team 1 negative z; Team 2 positive z |
| Character | Circle radius 0.45 m; visual height 1.8 m |
| Character centre limits | x ∈ [-5.55,5.55]; T1 z ∈ [-8.55,-0.45]; T2 z ∈ [0.45,8.55] |
| Spawn | T1 (0,-6); T2 (0,6) |
| Movement | 3.5 m/s × normalized input vector; diagonal magnitude capped at 1 |
| Balls | Exactly four; radius 0.30 m; stable IDs b1–b4 |
| Ball spawn | b1 (-2,-0.6), b2 (2,-0.6), b3 (-2,0.6), b4 (2,0.6) |
| Pickup | Centre distance ≤ 1.2 m; one held ball per character |
| No-throw zone | Character centre abs(z) ≤ 2.0 m, inclusive |
| Throw | Horizontal release; horizontal speed 8 + 6 × strength m/s, strength ∈ [0,1], constant for the whole flight |
| Ball gravity | 3.4 m/s² downward; release height 1.5 m; resting height is one ball radius |
| Flight lifetime | 2 seconds; no bounce; court exit or expiry triggers respawn. Touching down instead leaves the ball grounded where it lands |
| Respawn delay | 1 second at that ball's original spawn; no damage while respawning |
| Round | 60 seconds = 3600 active ticks |
| Countdown / result display | 3 seconds / 2 seconds |
| Match victory | Best of 3: first to 2 points ends the match; otherwise it ends after round 3 with the higher score winning and an equal score a drawn match (winner null). Draws award no point |
| Input timeout | 250 ms since server received last valid role input |

Input and aim use world x,z. T1 forward is +z; T2 forward is -z. Team-relative right maps +x for T1, -x for T2. Rendering maps (x,z) to PlayCanvas (x,0,z). The overview camera looks from negative z; the current renderer also supports independent Team 1 and Team 2 first-person views, selected from the screen's camera claim or with the `view` query override. A screen view changes presentation only.

## Acquisition, hold, aim, release

A rising Hold press enables pickup while moving; acquisition is retried each tick while Hold remains active. Choose nearest grounded ball in range; break equal-distance ties by ball ID. Already-latched holds retry in team-number order each tick. Fresh press edges acquire in server receive-ordinal order; the first successful acquisition wins. No ball can be acquired twice. Held balls follow the character and cannot block a throw. No catching, jumping, health, elimination, or friendly fire.

Aim must be finite, length in [0.99,1.01] before normalization and point into the opponent-facing hemisphere (T1 aim.z ≥ 0.2, T2 aim.z ≤ -0.2). Server normalizes valid aim and rejects zero or backward aim. Default aim is straight forward. A throw requires an existing held ball, active Hold, release action, current input epoch and active round. Gesture recognition happens on the phone, but the server alone decides whether release is legal. Strength is a bounded gesture estimate, never integrated physical velocity.

Release inside the no-throw zone is a safe cancellation: drop the held ball grounded at the character centre, clear Hold, and emit an input rejection notice NO_THROW_ZONE. Release without a valid phone gesture sends cancel instead of release. Cancel, stale input, focus loss, role change or disconnect drops the held ball without velocity or damage. Releasing without a ball clears Hold and has no gameplay effect. The player must press again to reacquire after cancellation. Grounded balls cannot damage anyone.

A valid throw launches the ball at character centre plus aim × 0.65 m, at release height 1.5 m, with no vertical velocity: aim is a 2D world direction and the phone has no vertical-aim channel, so every throw leaves the hand horizontally. Gravity of 3.4 m/s² then pulls it down, giving the descending half of a parabola — flat at first, then drooping. Horizontal speed is unaffected by gravity and stays constant. **The ball therefore never rises above its release height, and so never leaves the vertical extent of a 1.8 m character; collision stays the flat 2D test below and height is never an input to it.** When the ball centre reaches resting height it touches down and becomes an ordinary grounded ball exactly where it landed: no bounce, no roll, no respawn. It damages nobody from then on and either team may pick it up. Because every ball lands in well under a second, the 2 second lifetime is a safety net that normal play does not reach; court exit still ends a flight that crosses a wall first. Spin or a trail may be added visually. Its shooter team is remembered; only the opposing character can be hit. Sweep the ball segment against the opponent's movement segment (relative-motion swept circles, combined radius 0.75 m), preventing tunnelling. Compute earliest time of impact in the tick. Clip flight to wall/lifetime endpoint before testing; a hit at or before that endpoint counts. Ties use ball ID. If two opposing hits have equal time within 1e-9, award a draw, with no points.

## Deterministic step order

1. At tick start, if 3600 active ticks have elapsed, end a timeout draw before accepting throws.
2. Validate queued commands and preserve Arms edges/aim in server receive-ordinal order; choose the latest valid Legs movement per team. Ignore old epoch, duplicate or unauthorized commands.
3. Clear stale controls; apply movement and clamp centres to the appropriate half.
4. Retry previously latched holds in team-number order at the new positions. Replay Arms commands in receive-ordinal order: press enables Hold and immediately attempts pickup; aim updates aim; release uses its own aim and current possession, then clears Hold; cancel drops and clears Hold. Thus press+release in one tick works, release+cancel cannot undo an already legal throw, and a later aim cannot change an earlier release. Never collapse edges into a final button value.
5. Advance flight, resolve earliest valid hit, then respawns. A hit ends the round immediately; ignore later hit candidates.
6. Increment active tick and publish changed state. No commands affect results after phase leaves active.

This makes a throw received at the deadline ineligible; a hit during the last valid step counts. Use floats with stable iteration order and a seeded-free fixed setup; determinism means identical input ticks on the same Python runtime, not cross-language lockstep. Server timers derive from simulation ticks, not client clocks.

## Match state machine

`lobby → countdown → active → round_end → role_switch → countdown … → match_end`.

Host start is allowed only with exactly four connected ready calibrated phones and at least one connected screen. Reset scores on start. Countdown ignores all gameplay inputs. Every phase transition clears latched controls and increments input epoch; reset/abort in lobby also increments epoch; clients must use the new epoch. At active entry phones may send fresh movement but Hold starts false.

A hit awards one point; timeout or simultaneous hit awards none. Enter round_end, keep result visible for 2 seconds, and reset arena on entering role_switch. Swap the two phone IDs within each team after **every** round, including draws and the winning round. Increment assignment version and clear all readiness. If score reached 3, enter match_end after the swap; do not require calibration until rematch. Otherwise role_switch waits for all four phones to recalibrate and explicitly become ready, with at least one screen. Display “waiting for …”; never force-start an unready controller. Next countdown then active begins with reset balls/characters/timer and incremented round number.

Match_end displays winner and final score. Host rematch resets scores and arena, retains the final assignments, and returns to lobby for readiness. A match lasts at most 3 rounds, so all-draw play ends as a drawn match after round 3. Demo players deliberately make valid throws; no arbitrary timeout winner.

## Interruptions — deliberately minimal MVP recovery

A phone disconnect, original host disconnect or loss of all screens in any non-lobby phase resets the match to lobby immediately. A current-epoch phone ready=false during countdown/active does the same; in other phases it only clears that member’s readiness. Clear score, controls, held balls, timer and all readiness, reset arena, increment epoch and keep current assignments. No reconnect resume, frozen match, host migration or interrupted-phase storage. The UI states “Connection lost; ready again to restart.” Losing an extra screen while another remains only changes membership.

Alan retains disconnected member seats/tokens for 30 seconds. Returning within that time restores the member to lobby; phone recalibrates and explicitly readies. After grace remove disconnected non-host members; missing host closes room. A new phone may fill a vacant lobby slot. Server overload also resets to lobby with a clear error. Process restart loses the room entirely. Explicit host reset performs the same lobby reset. The old round does not award a point or trigger a role swap because it was aborted, not completed.

## Rules acceptance

Richard tests boundary clamps, diagonal speed, all four spawns, pickup tie, ownership uniqueness, forbidden throws, safe cancellation, swept hits, held-ball non-blocking, ball arc and landing point, landed-ball pickup, timeout boundary, simultaneous draw, exactly-once scoring, all round resets, winning-round swap, readiness gating, disconnect abort and rematch. Ryan shows zone, possession, score, phase, and server remaining time without deciding outcomes, and draws the ball at the published height. See [06](06-integration-and-testing.md) for the complete MVP traceability matrix.
