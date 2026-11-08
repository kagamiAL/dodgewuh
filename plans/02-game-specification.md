# Gameplay specification — rules authority

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

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
| Court | x ∈ [-6,6], z ∈ [-9,9] metres; y is visual height only |
| Team halves | Team 1 negative z; Team 2 positive z |
| Character | Circle radius 0.45 m; visual height 1.8 m |
| Character centre limits | x ∈ [-5.55,5.55]; T1 z ∈ [-8.55,-0.45]; T2 z ∈ [0.45,8.55] |
| Spawn | T1 (0,-6); T2 (0,6) |
| Movement | 3.5 m/s × normalized input vector; diagonal magnitude capped at 1 |
| Balls | Exactly four; radius 0.30 m; stable IDs b1–b4 |
| Ball spawn | b1 (-2,-0.6), b2 (2,-0.6), b3 (-2,0.6), b4 (2,0.6) |
| Pickup | Centre distance ≤ 1.2 m; one held ball per character |
| No-throw zone | Character centre abs(z) ≤ 2.0 m, inclusive |
| Throw | Straight 2D flight; speed 8 + 6 × strength m/s, strength ∈ [0,1] |
| Flight lifetime | 2 seconds; no bounce; expiry or court exit triggers respawn |
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

A valid throw launches the ball at character centre plus aim × 0.65 m. Its shooter team is remembered; only the opposing character can be hit. A visual arc or spin may be added, but flight height never alters collision. Sweep the ball segment against the opponent's movement segment (relative-motion swept circles, combined radius 0.75 m), preventing tunnelling. Compute earliest time of impact in the tick. Clip flight to wall/lifetime endpoint before testing; a hit at or before that endpoint counts. Ties use ball ID. If two opposing hits have equal time within 1e-9, award a draw, with no points.

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

Richard tests boundary clamps, diagonal speed, all four spawns, pickup tie, ownership uniqueness, forbidden throws, safe cancellation, swept hits, held-ball non-blocking, timeout boundary, simultaneous draw, exactly-once scoring, all round resets, winning-round swap, readiness gating, disconnect abort and rematch. Ryan shows zone, possession, score, phase, and server remaining time without deciding outcomes. See [06](06-integration-and-testing.md) for the complete MVP traceability matrix.
