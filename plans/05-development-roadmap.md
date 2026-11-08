# 24-hour working-MVP execution plan

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

24 hours is an upper planning bound; the actual remaining time is less. Target the functional four-phone hosted match by H12, preserve the remaining time for fixes, and drop optional interpolation/polish entirely if time is tight. The user's priority is **something working**. Do not spend time on features not needed for the acceptance scenario. Primitive geometry, text room codes, binary permission feedback, a large Hold button and simple physical controls are the product for this hackathon. No custom art, audio, QR generation, account system, replays, advanced gesture ML, analytics, prediction, precise displacement, or deployment automation beyond a repeatable shell script.

## Gates and schedule

| Time | Parallel work and merge window | Observable go/no-go gate / response |
|---|---|---|
| 0–0.5 h | All read 01→02→03→04; freeze contracts and ownership. Alan scaffolds backend/contracts; Ryan frontend. Tysen tests sensor permission immediately. | Everyone can name exact inputs/State and owned files. Record freeze commit. No subsystem redesign afterward. |
| 0.5–1 h | Richard movement stub/fixtures; Ryan mock character; Morteza Hold/cancel playground; Tysen real phone sensors; Alan room + hello and DNS/account check. | One iPhone reports finite motion over HTTPS; otherwise prioritize permission/secure-origin fix before gesture coding. |
| 1–2 h | Merge minimal Simulation interface, transport and renderer; physical lean emits Legs. Alan starts EC2 setup while Richard/Ryan pair on adapter. | Local backend supports authenticated screen+phone and fixture roundtrip; cloud delay cannot block local test. |
| 2–4 h | First integration window: real phone → FastAPI → Python → PlayCanvas. Other slots may be synthetic clients in this test only. | By H4, ten intentional moves in four directions; screen follows and stops on neutral/stale input. If missed, all relevant owners pair until fixed, cut polish. |
| 4–6 h | Arms press/acquire/release, simple gesture threshold; basic collision; cloud build served. | Two real phones jointly acquire and throw; cancellation cannot throw. Public HTTPS/WSS smoke by H6. Use fixed strength with motion-gated release; skip strength tuning. |
| 6–8 h | Merge all four controllers and deterministic hit scoring. | Four real phones, two characters, four balls; no-throw zone blocks release; one valid hit adds exactly one point. |
| 8–10 h | Role swap, ready gating, timeout draw, rematch; first full cloud match. | Both teammates use both roles; all four re-ready; best-of-3 winner and rematch work. Fix lifecycle before extra visuals. |
| 10–12 h | Connect second screen, disconnect/reset handling; run full deployed match. | Screens agree on score/phase/positions; disconnect stops input, returns lobby safely. H12 core gate: public four-phone full match. |
| 12–16 h | Real-device reliability, bounded queue/rate checks, instructions and performance tuning. | Three consecutive completed matches, zero accidental throws on tested cancel paths. Missing essentials take priority; no optional features. |
| 16–18 h | Buffer for integration defects; record fallback demo. | H18 FEATURE FREEZE: only fixes to broken acceptance cases; pin known-good release. |
| 18–21 h | Deployment rehearsal, rollback test, venue/hotspot test; stagger breaks. | Fresh room on clean browser + four real phones completes match twice. |
| 21–24 h | Demo rehearsal and stability buffer. | Two-to-three-minute demonstration twice, prepared backup, no dependency upgrades. |

Each listed integration window lasts 20–30 minutes inside its interval. Merge working partial slices every ~2 hours; leave main runnable. H4 is a target, not a claim the slice exists. Do not build an elaborate mock backend before routing a single real command.

## Critical path and budgets

Freeze → real sensor permission → normalized Legs → authenticated WebSocket → Simulation adapter → snapshot renderer → two-phone pickup/throw → four phones → scoring/role-switch/full match → cloud rehearsal. DNS/account checks begin H0 in parallel; usable HTTPS is a dependency of real-device testing, but not of simulation/render development.

Budget ~18 productive hours/person (90 person-hours total), leaving 6 hours/person for breaks, integration variability and presentation. Richard: 2 interfaces, 7 core mechanics, 4 lifecycle, 5 testing/integration. Ryan: 3 scaffold/mock, 5 renderer/UI, 4 phone shell/lobby, 6 integration/demo. Morteza: 2 sensors integration, 6 Arms, 4 real-phone tuning, 6 integration/repair. Tysen: 3 permission/playground, 5 Legs, 4 device coverage, 6 integration/repair. Alan: 3 contracts/bootstrap, 5 rooms/socket/adapter, 4 deployment, 3 lifecycle, 3 testing. These are coarse budgets; avoid adding optional tasks to Alan.

Richard supplies adapter examples and helps debug simulation integration without editing Alan's files; Ryan runs end-to-end smoke and logs failures; Tysen gathers phone compatibility evidence; Morteza tests network interruptions. Alan remains sole infrastructure editor. This is assistance through testing/review, not overlapping ownership.

## First 60 minutes

- Richard: read freeze docs, create pure DTO/Simulation skeleton and deterministic movement test; provide one complete snapshot fixture to Alan/Ryan.
- Ryan: bootstrap Vue/Vite/PlayCanvas, mount a primitive character from that fixture; export PhoneShell/session-store interfaces.
- Morteza: create Arms component with large Hold and cancel handling; record press/release edges with final message schema; test touch cancellation.
- Tysen: open HTTPS sensor playground on an iPhone, request permissions from a tap, display finite samples, implement neutral calibration and lean vector.
- Alan: commit protocol/fixture scaffolds, room creation and authenticated hello; verify AWS login, GoDaddy edit access and chosen hostname; start DNS provisioning once EIP exists.

## MVP scope gates

Use calibrated torso lean with a two-handed phone held at the waist from the outset; if continuous control is unreliable by H3, use dominant-axis lean sectors. Use fixed strength 0.5 with motion gating + release throughout the MVP; do not spend time tuning variable strength. If animation is incomplete, use capsules/spheres. If second-screen interpolation is troublesome by H12, render latest snapshots identically on both screens first, then smooth only if time remains. Additional screens must never become another simulation.

If cloud is late, develop against trusted local HTTPS and keep Alan on deployment. If the complete lifecycle is broken at H12, stop all cosmetics and pair on it. Role switching, four humans, physical controls, server authority, round scoring and HTTPS/WSS cannot be silently removed from the declared MVP. A one-screen or local-only fallback is a demonstration contingency, not evidence that the full requirements passed.
