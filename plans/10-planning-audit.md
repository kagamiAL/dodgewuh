# Pre-implementation audit — 2026-11-07

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

The package is suitable for a coordinated contract freeze after the corrections below. No implementation agents were started. This is a document/interface review, not evidence of a working game. The priority is a functional four-phone multiplayer match within the remaining hackathon time; optional interpolation, art and strength tuning must not delay that loop.

Reviewed all 19 core planning deliverables plus the master prompt and planning overrides. Retained the documented split between Richard simulation and Ryan rendering. Reviewed architecture, rules, protocol, ownership, schedule, mocks/testing, risks, deployment, demo, four workstream plans and five agent briefs. The original prompts remain historical inputs rather than implementation contracts.

## Integration blockers found and corrected

| Finding | Failure it could cause | Correction and owner |
|---|---|---|
| ready=false forbidden during active/countdown by event table, but required by interruption policy | Sensor loss rejected instead of resetting play | [03](03-api-contracts.md) permits revocation in every phase and defines its effect; Alan/Richard |
| Ready carried assignment_version but no epoch | Delayed pre-reset Ready could re-enable a phone without new calibration when assignments were unchanged | Added epoch in TS/Python/examples and explicit stale-status rejection; Alan/Ryan |
| PhoneShell only sent status after a tap and only remounted on role changes | Stale sensors did not reliably revoke readiness; reset/reconnect reused local calibration | Explicit calibrated/availability emits, automatic ready=false, reset/welcome remount and authoritative room readiness; Ryan/Morteza/Tysen |
| Transport had no connection-status subscription or terminal-close behavior | Controllers could remain enabled; superseded tabs could continually reconnect and evict each other | Defined status callback, welcome ordering, disconnected-send behavior and terminal close codes; Alan/Ryan |
| One timestamp covered two independent sensor streams | Fresh orientation could make cached throw acceleration appear recent | Per-stream receipt timestamps, role-specific required fields and expiry; Tysen/Morteza |
| Socket seq restarted but simulation duplicate-defense lifetime was unspecified | Reconnected phone seq=1 could be rejected indefinitely | Adapter owns socket seq; simulation uses room receive ordinal; superseded-socket cleanup cannot remove replacement; Alan/Richard |
| SimEvent/DTO and event-drain behavior left to implementers | Adapter and engine could disagree on event fields, readiness ownership or transition timing | Frozen DTO representation, named event records, synchronous versus deferred errors, drain-after-mutation and readiness mirroring defined; Richard/Alan |
| Same-tick press/release preservation lacked executable ordering | Fast press/release could lose pickup or use a later aim | Defined edge replay at updated positions and deterministic pickup ordering in [02](02-game-specification.md); Richard |
| Multiple phase transitions and separate pending snapshots lacked a barrier rule | Winning-round events or queued snapshots could regress displayed phase/epoch | Ordered transition bundles and discard/flush of prior snapshots; Alan/Ryan |
| Ryan was told to create component placeholders despite exclusive controller ownership | Agents could create conflicting files before the first merge | Each owner creates their own exports; root/backend and frontend manifests have separate single owners; all |

Additional clarifications: exact aim tolerance, initial state/timer rounding, lobby reset epoch, registration expiry, token invalidation on removal, and original-host versus additional-screen loss. Test plans now distinguish schema-invalid JSON from stateful authorization/lifecycle rejection; static validators cannot determine the currently authorized role or epoch.

## Parallel scaffold

Created 27 directories with empty `.gitkeep` files at the actual repository root, matching [04](04-repository-structure.md):

| Owner | Directories |
|---|---|
| Richard | backend/simulation |
| Ryan | frontend/src/stores; frontend/src/views; frontend/src/game; tests/e2e; docs/demo |
| Morteza | frontend/src/controllers/arms |
| Tysen | frontend/src/controllers/legs; frontend/src/sensors; frontend/src/playground; docs/device-tests |
| Alan | backend/app; frontend/src/net; frontend/src/generated; contracts/fixtures/valid; contracts/fixtures/invalid; infra; deploy; .github/workflows |

No manifests, application source, CI workflow or infrastructure implementation was created. Existing files were preserved. Use a separate branch and checkout/worktree per agent; do not switch branches in a shared working directory. Only the directory owner removes its .gitkeep. Alan owns shared backend/root files and Ryan owns shared frontend manifests. No commit or worktree has been created by this audit.

## Validation and limits

Validation passed: relative links across all 22 Markdown files; six fenced JSON examples; 17 inline JSON examples, including both updated controller.ready messages; Python schema syntax; and 26 corresponding TS/Python field sets (25 interface pairs plus Vec2). Full State examples passed required-field, two-character/four-ball and ownership-reference checks. All 27 owned .gitkeep files exist and are empty. This is structural validation; Pydantic/Zod runtime validators and application integration tests do not yet exist. Semantic review is what found the lifecycle gaps despite matching field names.

Rechecked that the sensor specification defines secure-context APIs with nullable fields; real phone behavior still needs H1 testing. [W3C Device Orientation and Motion](https://www.w3.org/TR/orientation-event/)

Rechecked Caddy's WebSocket support and its default connection closure on configuration reload; deploy/reload between matches. [Caddy reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)

Rechecked FastAPI's warning that its in-memory connection example is single-process; keep one worker as planned. [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)

No AWS/DNS access, certificate issuance, package installation, runtime schema tests, device trials or deployed multiplayer tests were performed. Exact package versions are deliberately chosen during bootstrap. Domain, quota, phone compatibility and venue latency remain the early experiments in [07](07-risks-and-fallbacks.md), not reasons to add infrastructure.

## Handoff gate

Freeze the amended 02/03/04 together in one shared commit before independent implementation. Read the shared package, then each workstream plan and brief. Alan and Ryan bootstrap their owned roots; other agents create only their owned exports against 03. First real phone movement by H4, cooperative throw/public HTTPS by H6, four phones by H8 and functional hosted full match by H12 remain the integration targets. Start integrating partial slices immediately; do not wait for complete subsystems. If those gates slip, pair on the failing path and cut optional work.
