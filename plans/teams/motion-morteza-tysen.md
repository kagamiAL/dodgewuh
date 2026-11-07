# Motion Team — Morteza and Tysen

Make modest physical movements reliably control two complementary roles. Morteza owns Arms; Tysen owns Legs and shared sensor capture. Ryan mounts their Vue components and sends readiness through PhoneShell: explicit true on Ready tap, automatic false on loss of calibration/availability, always with current epoch and assignment_version. Alan owns transport. Use [03](../03-api-contracts.md) without inventing events. Gameplay rules live in [02](../02-game-specification.md).

## Minimal common flow

Use portrait, phone held firmly; do not rely on pocket placement, compass heading, absolute displacement or double integration. Enable Motion button calls feature-detected DeviceMotionEvent.requestPermission and DeviceOrientationEvent.requestPermission from the same tap before awaiting unrelated operations. If neither method exists, subscribe and inspect data rather than assuming access. Handle denied/unsupported/null values distinctly. Native permissions are local, then report status through controller.ready. A second explicit button may be necessary if a browser requires another activation; test actual Safari behavior.

Tysen's SensorService is the one event source per phone and follows the exact local interface in [03]. Return finite values or null; preserve separate orientation/motion receipt times exactly as [03]. Never refresh cached motion with a new orientation timestamp. Emit calibrated(false) and availability status when required role data expires. Block landscape with rotate-and-recalibrate guidance rather than implementing arbitrary orientation transforms for MVP. Stop listeners when no subscribers remain. If required fields are absent, report unsupported; raw sensor data stays on device.

Calibration: hold neutral portrait pose steadily for 1 second, collect at least 15 valid orientation samples, average beta/gamma and estimate neutral noise. If insufficient data, show Retry and do not mark calibrated. Store only in memory for this role session. Recalibrate after role switch, orientation change, visibility loss or reconnect. Calibration UI displays neutral and live indicators, never a misleading “ready” while samples are stale.

## Legs — Tysen

Primary MVP scheme: phone held two-handed at waist facing user; lean/shift torso left/right and forward/back while keeping phone aligned with body. Map gamma relative to neutral to local right, beta relative to neutral to local forward (sign verified on actual device). This is meaningful body motion; no traditional joystick. Provide an on-screen arrow and a short “lean your body with the phone” instruction. Seated torso movement is permitted.

Algorithm starting values (controller tuning, not gameplay constants): low-pass orientation with time-based 80 ms smoothing; dead zone 6 degrees, full output at 20 degrees; signed linear scaling between, clamp each axis then normalize vector magnitude ≤1. Transform local direction to world by team mapping in [02]. Transmit input.legs at up to 20 Hz; send zero immediately on neutral transition, visibility loss or stale samples. After 250 ms without usable sample, zero and disable readiness. Do not use accelerometer position tracking. Test direction signs in playground before integration.

If continuous diagonal control is noisy by H3, use four sectors selected by dominant lean axis with 8-degree enter/5-degree exit hysteresis; retain physical lean. Step detection, jogging classifier and pocket controls are out of MVP. Do not implement both variants unless the test triggers fallback.

## Arms — Morteza

Large thumb-accessible Hold button at least 120 CSS px high; touch-action:none on control region, pointer capture, one active pointer ID, no text selection. UI states neutral/holding/gesture-ready/cancelled; authoritative possession comes from state. A press sends input.arms action=press, then aim-only samples at 20 Hz. A normal pointerup sends release only if held pointer is still valid and gesture threshold occurred recently; otherwise cancel. lostpointercapture after completed pointerup must not double-send. pointercancel, page hide, role unmount, transport loss and rotation cancel safely; never convert cancellation into release. Ask player to keep holding phone, not throw the device.

Aim: relative gamma tilt maps to yaw clamped ±60 degrees around team forward, smooth over 80 ms. Produce world normalized vector: T1 (sin(yaw),cos(yaw)); T2 (-sin(yaw),-cos(yaw)). Aim remains inside valid forward hemisphere. Avoid yaw compass requirements. Freeze the last pre-gesture aim when motion threshold is crossed so swing does not wildly alter intended aim.

Gesture starting thresholds: while holding, detect gravity-excluded acceleration magnitude ≥3 m/s² OR rotation-rate magnitude ≥120 deg/s; require a peak within 350 ms before normal pointerup. Thresholds are hypotheses to tune on real devices; stationary release cancels. Use fixed strength 0.5 for initial working slice. Variable strength is outside this working MVP; the bounded strength field leaves room for later experimentation after all acceptance gates. Never integrate acceleration to velocity. If acceleration is null but rotation_rate is valid, use rotation threshold. If both unavailable, block Arms readiness and use a tested phone.

Server decides pickup, possession, zone and release legality. UI may show “move back to throw” from state position, but cannot prevent server validation. After release/cancel require fresh press. Display server rejection text without replaying input. Debug controls are not the actual demo input method.

## Isolation, order and ownership

Tysen owns frontend/src/sensors/**, controllers/legs/**, playground/** and corresponding tests/docs in [04]. Morteza owns controllers/arms/** and tests/arms/**. Ryan owns PhoneShell/router/dependency files; send him route/import requests. Alan owns net/generated types. Do not each implement separate permission or WebSocket services.

1. H0–1 Tysen supplies SensorService stub and actual iPhone sample report; Morteza builds Hold/cancel against recorded SensorSample fixtures.
2. H1–2 playground `/sensors` shows raw beta/gamma/accel/rate, neutral baseline, vector/aim, gesture indicator, sample age and outgoing validated messages. No backend required.
3. H2–4 Tysen connects Legs to real transport for vertical slice; Morteza tests 20 deliberate gestures and cancellation paths.
4. H4–6 pair with Richard/Ryan on pickup/aim/release; use final server possession to update UI.
5. H6–10 four actual phones, each exercised in both roles after server role switch.
6. H10–16 verify background/reconnect, record exact models/OS/network, fix only reproducible control problems.

## Acceptance and done

- [ ] Permission denial gives actionable retry/browser guidance and never marks Ready.
- [ ] Neutral produces zero; ten trials per direction reach ≥9 correct, stop reliably.
- [ ] ≥18/20 deliberate gesture/releases detected with fixed strength; stationary and cancelled releases never launch.
- [ ] Two phones genuinely required for movement + throwing; both teams work simultaneously.
- [ ] Swaps clear touch/calibration and old epoch commands; both components mount on all demo phones.
- [ ] Local replay tests and actual Safari tests documented; no raw sensors transmitted.

Done means physical control works in deployed match, tests in [06](../06-integration-and-testing.md) pass and component interfaces match [03]. Handoff to Ryan: props/emits, readiness/calibration behavior, route imports. To Alan: rejected message traces without tokens. To Richard: representative valid vectors/actions and observed delay. Tysen publishes device compatibility table; Morteza publishes gesture threshold results and cancellation checklist. No claim of universal device support.
