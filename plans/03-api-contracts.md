# Shared API contracts — protocol v1 authority

> **Current project instruction — dodgewuh:** Do not create automated tests, test files, test suites, test harnesses or test-only dependencies. Do not add pytest, Vitest or Playwright, or require automated test commands for milestones, handoffs or deployment. Verify work through builds, type checks, runtime validation and manual API, browser, device and multiplayer checks. Keep useful protocol examples and runtime validators. Any remaining historical references to tests or test directories are not instructions to implement them. This instruction supersedes earlier testing requirements in this document.

This is the sole normative network schema source. Alan owns implementations in Python and TypeScript, fixture examples and validation. Richard owns the pure simulation DTO mirror and manual adapter compatibility checks; no framework dependency enters simulation. [02](02-game-specification.md) owns gameplay numbers. All clients and mocks implement this protocol without temporary event names.

## Conventions and validation

JSON UTF-8, snake_case fields in both languages, no undefined values. Required nullable fields must be present as null. Reject unknown fields, NaN/infinity, boolean-as-number, unknown event/version and out-of-range numbers. ID is opaque nonempty string ≤64 characters, UUID generated for room/member IDs; ball IDs follow [02]. Code is six uppercase characters from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`; retry collision against existing rooms. Name is trimmed 1–24 characters. seq, tick, epoch and revision are nonnegative safe integers (≤2^53−1). All elapsed times are integer milliseconds. server_ms is monotonic milliseconds since this process boot, only comparable within one connection generation; never a Unix date. Clients use performance.now() for local elapsed times. No gameplay decision trusts a client timestamp.

Coordinates are `{x,z}` world metres or normalized world directions per [02]. Input seq increases across ALL input event types within a socket, starts at 1 after welcome. The adapter rejects seq ≤ last accepted seq for this socket generation; initial last seq is 0. Simulation uses room-wide receive ordinal for duplicate defense, not a member-lifetime seq counter, so reconnect seq=1 is valid. It stamps accepted input with receive ordinal and receipt time. Commands never carry player/team identity: derive those from the authenticated member and simulation assignment. `camera.claim` is the exception that selects an explicit team for an authenticated screen; the server authorizes screens only and routes their `input.legs` to that team's current Legs assignment. Each command carries epoch; every phase change and connection interruption invalidates old epoch. No input buffering/replay across reconnection or phase change.

## REST

All responses use JSON, including errors `{code: string, message: string}`. No REST authentication required for creation/join; both are rate limited. `Cache-Control: no-store` on membership responses. No public room listing.

| Method/path | Body / success | Failure |
|---|---|---|
| GET /api/health | no body → 200 Health | 503 if service not ready |
| POST /api/rooms | CreateRoom → 201 Registration; creates and registers host screen atomically | 422 malformed; 429 capacity/rate |
| POST /api/rooms/{room_code}/members | JoinRoom → 201 Registration | 404 absent; 409 full/phone join during match; 422 malformed; 429 rate |
| DELETE /api/rooms/{room_code}/members/me | Bearer token, no body → 204 | 401 invalid token; 404 room |

Screen join allowed in any phase. New phone joins only lobby; reconnect uses existing token. Local Compose currently configures `DEV_ORIGINS=*` for hackathon/tunnel use; production should configure explicit origins. Normalize code by trim+uppercase before lookup. Delete host closes room; delete phone in a match invokes disconnect policy. Health exposes build and room count, not tokens or member details. Limit creation to 5/min/IP, join to 30/min/IP, max 10 rooms/process, idle lobby TTL 30 minutes, empty room TTL 5 minutes, hard room TTL 4 hours. Expiration sends room.closed before closing sockets where possible.

## TypeScript data definitions

These definitions describe the implemented protocol v1 wire shape; the checked-in Python/TypeScript implementations and `contracts/protocol.schema.json` are generated/maintained from this contract.

```ts
type ID = string;
type Team = 1 | 2;
type Role = 'arms' | 'legs';
type Device = 'screen' | 'phone';
type Phase = 'lobby' | 'countdown' | 'active' | 'round_end' | 'role_switch' | 'match_end';
type Permission = 'unknown' | 'granted' | 'denied' | 'unsupported';
type Vec2 = { x: number; z: number };
interface CreateRoom { name: string }
interface JoinRoom { name: string; device: Device }
interface Registration { room_id: ID; room_code: string; member_id: ID; token: string; ws_path: string }
interface Health { status: 'ok'; build: string; rooms: number }
interface RestError { code: string; message: string }
interface Assignment { member_id: ID; team: Team; role: Role }
interface Member { member_id: ID; name: string; device: Device; connected: boolean;
  ready: boolean; permission: Permission; calibrated: boolean; camera_team: Team | null }
interface Room { room_id: ID; room_code: string; host_id: ID; revision: number;
  members: Member[]; assignments: Assignment[]; assignment_version: number; phase: Phase }
interface Character { team: Team; pos: Vec2; aim: Vec2; held_ball_id: ID | null }
interface Ball { ball_id: ID; mode: 'ground' | 'held' | 'flying' | 'respawning';
  pos: Vec2; velocity: Vec2; owner_team: Team | null; shooter_team: Team | null;
  respawn_in_ms: number }
interface Result { reason: 'hit' | 'timeout' | 'simultaneous'; winner: Team | null;
  hit_ball_id: ID | null; victim_team: Team | null }
interface State { tick: number; epoch: number; round: number; phase: Phase;
  remaining_ms: number; phase_remaining_ms: number | null; score: { t1: number; t2: number };
  characters: Character[]; balls: Ball[]; assignments: Assignment[]; assignment_version: number;
  result: Result | null; winner: Team | null }
interface Hello { token: string }
interface Ping { nonce: number }
interface Ready { epoch: number; assignment_version: number; ready: boolean; permission: Permission; calibrated: boolean }
interface Empty {}
interface Legs { seq: number; epoch: number; move: Vec2 }
interface CameraClaim { team: Team | null }
interface Arms { seq: number; epoch: number; aim: Vec2;
  action: 'aim' | 'press' | 'release' | 'cancel'; strength: number | null }
interface Welcome { member_id: ID; room: Room; state: State }
interface RoomUpdate { room: Room }
interface Snapshot { state: State }
interface PhaseChange { state: State }
interface RolesChanged { assignments: Assignment[]; assignment_version: number; epoch: number }
interface ErrorPayload { code: string; message: string; ref_seq: number | null }
interface Closed { reason: 'host_left' | 'expired' | 'server_shutdown' }
interface ClientPayloads {
  'session.hello': Hello; 'session.ping': Ping; 'controller.ready': Ready;
  'match.start': Empty; 'match.reset': Empty; 'match.rematch': Empty;
  'input.legs': Legs; 'input.arms': Arms; 'camera.claim': CameraClaim;
}
interface ServerPayloads {
  'session.welcome': Welcome; 'session.pong': Ping; 'room.updated': RoomUpdate;
  'state.snapshot': Snapshot; 'phase.changed': PhaseChange; 'roles.changed': RolesChanged;
  'error': ErrorPayload; 'room.closed': Closed;
}
type ClientMessage = { [K in keyof ClientPayloads]: {v: 1; type: K; payload: ClientPayloads[K]} }[keyof ClientPayloads];
type ServerMessage = { [K in keyof ServerPayloads]: {v: 1; type: K; server_ms: number; payload: ServerPayloads[K]} }[keyof ServerPayloads];
```

State always has exactly two characters sorted by team and four balls sorted by ID; lobby state also contains reset entities, round 0 and score zero. Assignments may be incomplete in lobby, exactly four during a match. Team/role uniqueness applies. Room and State assignments must match at one revision boundary. State tick is monotonically increasing for the room lifetime, including phase timers; active round elapsed is separate internal state. epoch never decreases, including reset/rematch. phase_remaining_ms is countdown/result remaining or null when waiting. winner is non-null only at match_end. result persists through round_end and role_switch, clears at next countdown; match_end retains final result. Ball ownership is non-null only held; shooter_team only flying; non-flying velocity is zero, respawn_in_ms zero except respawning.

## Corresponding Pydantic v2 schemas

Implement the following exact schema mapping; `Literal` enumerations mirror TS above. Alias types enforce wire-level numeric restrictions. Add model validators for cross-field/vector/list invariants described here. Strict integer fields reject booleans; Fin accepts JSON integer or float but never booleans/nonfinite. Configure JSON decoding to reject nonfinite constants too.

```python
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator

def numeric(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError('number required')
    return v

Fin = Annotated[float, BeforeValidator(numeric), Field(allow_inf_nan=False)]
UInt = Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
ID = Annotated[str, Field(min_length=1, max_length=64)]
Name = Annotated[str, Field(min_length=1, max_length=24)]
Team = Literal[1, 2]
Role = Literal['arms', 'legs']
Device = Literal['screen', 'phone']
Phase = Literal['lobby','countdown','active','round_end','role_switch','match_end']
Permission = Literal['unknown','granted','denied','unsupported']
class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')
class Vec2(Model):
    x: Fin
    z: Fin
class CreateRoom(Model):
    name: Name
class JoinRoom(CreateRoom):
    device: Device
class Registration(Model):
    room_id: ID
    room_code: str
    member_id: ID
    token: str
    ws_path: str
class Health(Model):
    status: Literal['ok']
    build: str
    rooms: UInt
class RestError(Model):
    code: str
    message: str
class Assignment(Model):
    member_id: ID
    team: Team
    role: Role
class Member(Model):
    member_id: ID
    name: Name
    device: Device
    connected: bool
    ready: bool
    permission: Permission
    calibrated: bool
    camera_team: Team | None
class Room(Model):
    room_id: ID
    room_code: str
    host_id: ID
    revision: UInt
    members: list[Member]
    assignments: list[Assignment]
    assignment_version: UInt
    phase: Phase
class Character(Model):
    team: Team
    pos: Vec2
    aim: Vec2
    held_ball_id: ID | None
class Ball(Model):
    ball_id: ID
    mode: Literal['ground','held','flying','respawning']
    pos: Vec2
    velocity: Vec2
    owner_team: Team | None
    shooter_team: Team | None
    respawn_in_ms: UInt
class Result(Model):
    reason: Literal['hit','timeout','simultaneous']
    winner: Team | None
    hit_ball_id: ID | None
    victim_team: Team | None
class Score(Model):
    t1: UInt
    t2: UInt
class State(Model):
    tick: UInt
    epoch: UInt
    round: UInt
    phase: Phase
    remaining_ms: UInt
    phase_remaining_ms: UInt | None
    score: Score
    characters: list[Character]
    balls: list[Ball]
    assignments: list[Assignment]
    assignment_version: UInt
    result: Result | None
    winner: Team | None
class Hello(Model):
    token: str
class Ping(Model):
    nonce: UInt
class Ready(Model):
    epoch: UInt
    assignment_version: UInt
    ready: bool
    permission: Permission
    calibrated: bool
class Empty(Model):
    pass
class CameraClaim(Model):
    team: Team | None
class Legs(Model):
    seq: UInt
    epoch: UInt
    move: Vec2
class Arms(Model):
    seq: UInt
    epoch: UInt
    aim: Vec2
    action: Literal['aim','press','release','cancel']
    strength: Fin | None
class Welcome(Model):
    member_id: ID
    room: Room
    state: State
class RoomUpdate(Model):
    room: Room
class Snapshot(Model):
    state: State
class PhaseChange(Snapshot):
    pass
class RolesChanged(Model):
    assignments: list[Assignment]
    assignment_version: UInt
    epoch: UInt
class ErrorPayload(Model):
    code: str
    message: str
    ref_seq: UInt | None
class Closed(Model):
    reason: Literal['host_left','expired','server_shutdown']
```

For each event in the TS ClientPayloads/ServerPayloads maps, define a Pydantic envelope subclass with `v: Literal[1]`, `type: Literal[exact_event_name]`, and `payload: corresponding class`. Server subclasses additionally require `server_ms: UInt`. Build client/server discriminated unions using `Field(discriminator='type')`. This table-driven envelope mapping is normative; no open-ended dict payloads. Runtime TS validation uses Zod schemas with strict objects mirroring these classes; TS Empty alone is not sufficient validation. bool fields must be strict; enum Team and v validators must reject booleans and numeric strings explicitly. Export JSON Schema from Pydantic and validate the shared good/bad JSON fixture corpus in Python and TS.

## WebSocket lifecycle and event semantics

Connect same-origin `/ws/rooms/{room_code}` (wss in production). First message session.hello within 5 seconds; otherwise close 4401. Origin check before upgrade, token validation after upgrade. Local Compose sets `DEV_ORIGINS=*` for hackathon testing, while deployment must use an explicit allowed origin. No query credentials. One live socket/member: a new successful hello supersedes the prior socket with 4409. For a phone or original host this clears input and resets an underway match to lobby; replacing an additional screen does not reset gameplay. Cleanup from a superseded socket must not disconnect its replacement. Token remains valid until member removal or room closure; reconnect backoff 0.5,1,2,4,5 seconds with jitter. Missing room closes 4404; policy/rate violation 4400/4429. Never replay throw events after reconnect.

| Event | Direction / allowed sender | Effect / delivery |
|---|---|---|
| session.hello | any registered client → server | authenticate; only once per socket |
| session.welcome | server → connecting member | full room/state baseline; reset buffers and seq |
| session.ping / session.pong | client → server / direct reply | every 5 seconds; echo nonce; no input effect |
| controller.ready | phone → server | ready=false allowed in every phase; ready=true only in lobby/role_switch; current epoch AND assignment_version required; true requires granted + calibrated |
| match.start | original host screen → server | lobby readiness check then simulation start |
| match.reset | host → server | any phase → lobby, zero score, clear ready, reset arena; preserve assignments |
| match.rematch | host → server | match_end → lobby, reset as above |
| input.legs | current Legs phone or screen with a camera claim → server | active only; latest movement, components [-1,1], vector magnitude ≤1.001; normalize slight excess |
| camera.claim | screen → server | select team 1/2 to claim its Legs control, or null to release; latest claim for a team wins |
| input.arms | current Arms phone → server | active only; aim every sample, action edges immediate; strength required [0,1] only release, null otherwise |
| room.updated | server → all | reliable full membership/readiness/assignment/phase record whenever changed; revision increments |
| state.snapshot | server → all screens AND phones | full state at 20 Hz during match; lobby baseline/on changes; not a delta |
| phase.changed | server → all | reliable complete new state at phase boundaries, including hit/round end/reset/match end |
| roles.changed | server → all | reliable assignment mapping after simulation swaps; clear sensors/Hold and readiness |
| error | server → offending client | structured rejection, ref_seq for input else null; does not mutate gameplay except safe cancel specified in [02] |
| room.closed | server → all | host exit/expiry/shutdown; clients stop sensors then close |

There are intentionally no client hit/score/ball-update events. Ball ownership is in state.snapshot, a successful hit and round ending in phase.changed.state.result, next round in phase.changed, and disconnection in room.updated. These fully specified state events cover all required actions without redundant schemas. On phase/role transition enqueue phase.changed, then roles.changed if applicable, then room.updated, then snapshot, all from the same completed mutation. For multiple transitions, preserve each transition bundle in order: phase.changed, its roles.changed if any, its room.updated; append only the final snapshot. Flush older pending snapshots before a transition barrier (or discard them), never send them afterward. Clients never apply a lower epoch or assignment_version, even at equal tick.

Transport rates: sensor sampling follows browser availability, target 30–60 Hz; motion/aim transmission 20 Hz max plus immediate Arms edges (cap 10/s). Per-socket allowance 40 messages/s with burst 60; 8 KiB client frames. Keep reliable command edges FIFO; coalesce movement/aim-only commands between edges. Never coalesce across press/release/cancel. Per-room input queue 128; on overflow safely cancel the sender and disconnect it. Valid input receipt time drives stale timeout, not ping. Heartbeat timeout 15 seconds; observed required-device socket close or phone ready=false during play resets to lobby. Sensor silence for 250 ms sends zero/cancel locally and ready=false. Backgrounding does likewise before suspension if possible; server stale control timeout remains the backstop.

Phones send status through controller.ready; granted means every sensor required for selected mode is available, feature-detected and producing finite fresh samples. Permission request is a local browser user gesture, not a WebSocket command. Initial controller.ready can report ready=false and unknown/denied/unsupported. Ready false during active/countdown resets to lobby, clearing every readiness flag. Required-device loss immediately resets any underway match; do not preserve interrupted gameplay. Unconnected registrations and disconnected lobby reservations expire after 30 seconds measured on backend monotonic time; host reservation expiry closes room. Reconnect restores identity, then calibration/readiness and a fresh host start are required. Additional non-host screen loss only changes membership while another screen remains; original host loss always aborts an underway match.

## Synchronization

Server emits server_ms on every message. Latest-snapshot rendering is the default MVP. If interpolation is added after multiplayer works, estimate offset from ping/pong midpoint using lowest RTT sample; render target server time now−100 ms. Interpolate only consecutive snapshots from the same epoch/round; never interpolate discrete ownership or scores. Ignore older tick snapshots; permit multiple same-tick reliable events in socket order. If no snapshot for 500 ms during a match, freeze transforms and show stale status. At 2 seconds reconnect; clear buffer on welcome. HUD clock may count visually between snapshots but cannot emit timeout or scores. Two screens must agree on tick-matched positions, score and phase, with observed presentation skew target ≤150 ms on venue Wi-Fi. Latency target p95 motion-to-visible response ≤300 ms, subject to real measurements.

## Pure simulation integration seam

Richard implements `Simulation` in `backend/simulation/engine.py`, plain immutable DTOs in `types.py`. All methods synchronous and socket-free:

- `Simulation(assignments: tuple[Assignment,...])`: initial lobby state; incomplete mapping permitted.
- `set_assignments(assignments) -> None`: lobby only; adapter supplies slot membership; simulation increments assignment_version when mapping changes and owns swaps thereafter. Empty slots are filled by the missing team/role pair in canonical slot order, preserving existing lobby assignments.
- `set_readiness(ready_member_ids: frozenset[str], connected_member_ids: frozenset[str], screen_count: int, host_connected: bool) -> None`: adapter passes facts; simulation gates progression.
- `control(action: Literal['start','reset','rematch','abort'], reason: str | None = None) -> None`: adapter authorizes host actions and invokes abort for transport failures; simulation validates phase and implements state changes. Invalid calls raise `SimulationError(code,message)`.
- `apply_input(member_id: str, command: LegsCommand | ArmsCommand, received_ms: int, ordinal: int) -> None`: pure DTOs with exact payload fields from above; enqueue for next step; verify role/epoch again in simulation.
- `step(now_ms: int) -> None`: exactly one fixed step; supplied monotonic time only for stale input checks. Active clock is tick-based.
- `snapshot() -> StateDTO`: defensive immutable full State equivalent above.
- `drain_events() -> list[SimEvent]`: ordered immutable `phase.changed`/`roles.changed` payload equivalents or targeted `error` with member_id; exactly once drain. Adapter maps into wire models and updates room readiness/assignments atomically before broadcasting.

Adapter owns disconnected-seat expiry and room closure; simulation implements abort as a complete reset to lobby. There is no resume operation. After reconnect use normal readiness/start. Simulation does not import Pydantic: Alan converts validated network models to DTOs and DTOs to Pydantic. MockSimulation implements these exact methods with scripted fixtures; it is used only in tests, never as a second production authority.

## Frontend module seams

Alan's `Transport` exposes `connect(registration): Promise<void>`, `send(message: ClientMessage): void`, `subscribe(handler: (message: ServerMessage) => void): () => void`, `close(): void`. It attaches hello, manages ping/reconnect, but callers provide typed messages; input seq is allocated centrally via `nextInputSeq(): number`. Ryan's session store applies room/state/role updates and provides components reactive current epoch, assignment and connection status. Tysen's `SensorService` exposes `requestPermissionFromGesture(): Promise<Permission>`, `subscribe(handler: (sample: SensorSample) => void): () => void`, `stop(): void`. SensorSample is local-only `{time_ms:number, orientation_ms:number|null, motion_ms:number|null, beta_deg:number|null, gamma_deg:number|null, accel:{x:number,y:number,z:number}|null, rotation_rate:{alpha:number,beta:number,gamma:number}|null}`; acceleration is gravity-excluded m/s², rotations deg/s. For MVP Tysen blocks landscape until portrait and recalibration. time_ms is sample emission time; orientation_ms and motion_ms are the last respective browser-event receipt times on performance.now(), null before any event. A cached stream never gets a fresh timestamp from the other stream. Legs requires fresh finite beta/gamma; Arms additionally requires fresh finite acceleration OR rotation_rate. Each required stream expires at age >=250 ms; null fields are unavailable, never zero-filled. Permission return reports API access; components determine usable fields for their role.

Both role components accept props `{transport, sensors, member_id, team, epoch, assignment_version, state, connected}` and emit local `calibrated(boolean)` to Ryan's PhoneShell. Components additionally emit availability(Permission), using granted only while required role samples are usable. Shell sends ready=true only after explicit Ready tap with current epoch/assignment_version and granted+calibrated. When availability ceases to be granted or calibrated becomes false, Shell immediately sends ready=false if connected; it does not wait for a tap. On welcome, lobby reset or assignment change, clear local readiness/calibration and remount the role component; countdown/active epoch changes only clear local input latches, not calibration. Room readiness is authoritative. Never reuse a Ready intent across epochs or reconnects; a stale rejection requires a fresh tap. Shell never generates gameplay commands. Arms and Legs own calibration and their commands. Sensor playground uses the same components/services and a recording Transport mock with schema validation.


### Minimal implementation details shared by all consumers

Transport is a named exported interface in `frontend/src/net/transport.ts`; `nextInputSeq(): number` is its method. Add `subscribeStatus(handler: (status: 'connecting' | 'connected' | 'reconnecting' | 'closed') => void): () => void`, delivering current status immediately on subscription. connected means welcome has been validated and delivered to message subscribers. connect resolves only then; close stops retries and clears buffers. send while not connected drops gameplay messages (never queues/replays them); consumers gate controls on status. Retry transient loss with the documented backoff; 4401/4404/4409, room.closed and explicit close are terminal and show rejoin/room-ended UI. In particular, a superseded tab must not reconnect and evict its replacement. Reset seq before delivering each welcome. Subscribe before connect.

`SensorService` and `SensorSample` are named exports from `frontend/src/sensors/sensorService.ts`. Permission acquisition attaches capture listeners; subscriptions share one capture service, unsubscribe releases that subscriber, and stop removes all listeners. Subscribe again after permission is already granted restarts capture. Controller default exports are `frontend/src/controllers/arms/ArmsController.vue` and `frontend/src/controllers/legs/LegsController.vue`. Props in the preceding paragraph use generated ID/Team/State and Transport/SensorService types; connected is boolean, epoch/assignment_version are numbers. These exports and the two local emits are also the mock contract.

Python DTOs in `backend/simulation/types.py` are frozen dataclasses. StateDTO and its nested records use the exact wire field names; wire arrays become tuples. LegsCommand/ArmsCommand have exactly Legs/Arms fields; Vec2 is a frozen x/z record. Enum values remain the documented literal strings/integers. SimEvent is the union of frozen `PhaseChanged(state: StateDTO)`, `RolesChanged(assignments: tuple[Assignment,...], assignment_version: int, epoch: int)` and `InputRejected(member_id: str, code: str, message: str, ref_seq: int | None)`. Adapter dispatches on these classes and constructs wire envelopes. SimulationError exposes code/message. Synchronous input validation failures raise SimulationError; deferred step rejections emit InputRejected, never both for one rejection.

After every simulation mutation (control, set_assignments, set_readiness or step), the adapter drains events exactly once before its next mutation, mirrors final assignments/phase into Room and publishes captured transition bundles. Simulation clears its internal ready set on swap/reset/abort/rematch; adapter clears Member.ready/calibrated at the same boundaries before passing readiness facts again. set_readiness only updates facts; automatic role_switch -> countdown happens on the next step. A reset while already in lobby still increments epoch and emits PhaseChanged(lobby), so old readiness/input cannot restart it. Lobby assignment changes invalidate all readiness. No extra readiness event or game authority is introduced.

Ready validation order is authentication, epoch, assignment_version, phase, readiness prerequisites. Reject stale status without mutation. A current ready=false in countdown/active aborts once; in other phases it only clears that member's readiness. A required-device disconnect aborts any non-lobby phase. No duplicate abort from socket cleanup. Initial state uses tick=epoch=assignment_version=round=0 for empty assignments; mapping changes increment assignment_version; remaining_ms=60000 and phase_remaining_ms=null in lobby. Timed phase milliseconds use ceil(remaining_ticks * 1000 / 60). Tick advances once per step in every phase and never resets.

Aim validation uses the length bounds in [02], normalized before checking the team hemisphere; reject anything outside. Snapshot aim is normalized. Cancel uses the last valid aim (or team forward), so stale sensors do not require invalid/null aim to stop Hold.

## Complete message examples and lifecycle trace

All examples are full wire objects unless REST is stated. Example IDs p1..p4 and s1 are readable substitutes for opaque production IDs.

1. Create: POST /api/rooms body `{"name":"Main screen"}` → `{"room_id":"r1","room_code":"ABC234","member_id":"s1","token":"opaque-host-token","ws_path":"/ws/rooms/ABC234"}`.
2. Join screen: POST /api/rooms/ABC234/members `{"name":"Projector","device":"screen"}` → `{"room_id":"r1","room_code":"ABC234","member_id":"s2","token":"opaque-screen-token","ws_path":"/ws/rooms/ABC234"}`.
3. Join phone: same endpoint `{"name":"Richard","device":"phone"}` → `{"room_id":"r1","room_code":"ABC234","member_id":"p1","token":"opaque-phone-token","ws_path":"/ws/rooms/ABC234"}`. Authenticate `{"v":1,"type":"session.hello","payload":{"token":"opaque-phone-token"}}`.
4. Assignment/change: `{"v":1,"type":"roles.changed","server_ms":100,"payload":{"assignments":[{"member_id":"p1","team":1,"role":"arms"},{"member_id":"p2","team":1,"role":"legs"},{"member_id":"p3","team":2,"role":"arms"},{"member_id":"p4","team":2,"role":"legs"}],"assignment_version":1,"epoch":0}}`. Initial assignment arrives in welcome/room.updated; this event illustrates the identical mapping structure used for swaps.
5. Permission: tap Enable motion, call feature-detected browser permission methods in that gesture; no network permission request. Report `{"v":1,"type":"controller.ready","payload":{"epoch":0,"assignment_version":1,"ready":false,"permission":"granted","calibrated":false}}`.
6. After calibration/Ready: `{"v":1,"type":"controller.ready","payload":{"epoch":0,"assignment_version":1,"ready":true,"permission":"granted","calibrated":true}}`.
7. Legs: `{"v":1,"type":"input.legs","payload":{"seq":1,"epoch":2,"move":{"x":0.6,"z":0.8}}}`.
8. Aim: `{"v":1,"type":"input.arms","payload":{"seq":1,"epoch":2,"aim":{"x":0,"z":1},"action":"aim","strength":null}}`.
9. Hold: `{"v":1,"type":"input.arms","payload":{"seq":2,"epoch":2,"aim":{"x":0,"z":1},"action":"press","strength":null}}`.
10. Throw: `{"v":1,"type":"input.arms","payload":{"seq":3,"epoch":2,"aim":{"x":0,"z":1},"action":"release","strength":0.5}}`.

11–12. Full snapshot with ownership (all other state messages embed exactly this State shape):

```json
{"v":1,"type":"state.snapshot","server_ms":5000,"payload":{"state":{"tick":300,"epoch":2,"round":1,"phase":"active","remaining_ms":58000,"phase_remaining_ms":null,"score":{"t1":0,"t2":0},"characters":[{"team":1,"pos":{"x":-2,"z":-1},"aim":{"x":0,"z":1},"held_ball_id":"b1"},{"team":2,"pos":{"x":0,"z":6},"aim":{"x":0,"z":-1},"held_ball_id":null}],"balls":[{"ball_id":"b1","mode":"held","pos":{"x":-2,"z":-1},"velocity":{"x":0,"z":0},"owner_team":1,"shooter_team":null,"respawn_in_ms":0},{"ball_id":"b2","mode":"ground","pos":{"x":2,"z":-0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0},{"ball_id":"b3","mode":"ground","pos":{"x":-2,"z":0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0},{"ball_id":"b4","mode":"ground","pos":{"x":2,"z":0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0}],"assignments":[{"member_id":"p1","team":1,"role":"arms"},{"member_id":"p2","team":1,"role":"legs"},{"member_id":"p3","team":2,"role":"arms"},{"member_id":"p4","team":2,"role":"legs"}],"assignment_version":1,"result":null,"winner":null}}}
```

The following are complete messages for independent scenarios, not a physically integrated replay. Alan stores these as valid fixtures.

13–14. Successful hit and round end are one authoritative phase event:

```json
{"v":1,"type":"phase.changed","server_ms":6000,"payload":{"state":{"tick":360,"epoch":3,"round":1,"phase":"round_end","remaining_ms":57000,"phase_remaining_ms":2000,"score":{"t1":1,"t2":0},"characters":[{"team":1,"pos":{"x":-2,"z":-1},"aim":{"x":0,"z":1},"held_ball_id":null},{"team":2,"pos":{"x":0,"z":6},"aim":{"x":0,"z":-1},"held_ball_id":null}],"balls":[{"ball_id":"b1","mode":"flying","pos":{"x":0,"z":5.4},"velocity":{"x":0,"z":11},"owner_team":null,"shooter_team":1,"respawn_in_ms":0},{"ball_id":"b2","mode":"ground","pos":{"x":2,"z":-0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0},{"ball_id":"b3","mode":"ground","pos":{"x":-2,"z":0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0},{"ball_id":"b4","mode":"ground","pos":{"x":2,"z":0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0}],"assignments":[{"member_id":"p1","team":1,"role":"arms"},{"member_id":"p2","team":1,"role":"legs"},{"member_id":"p3","team":2,"role":"arms"},{"member_id":"p4","team":2,"role":"legs"}],"assignment_version":1,"result":{"reason":"hit","winner":1,"hit_ball_id":"b1","victim_team":2},"winner":null}}}
```

15. Switching roles (all readiness clears in subsequent room.updated):

```json
{"v":1,"type":"roles.changed","server_ms":8000,"payload":{"assignments":[{"member_id":"p1","team":1,"role":"legs"},{"member_id":"p2","team":1,"role":"arms"},{"member_id":"p3","team":2,"role":"legs"},{"member_id":"p4","team":2,"role":"arms"}],"assignment_version":2,"epoch":4}}
```

16. Starting the next round, followed by active entry after countdown:

```json
{"v":1,"type":"phase.changed","server_ms":12000,"payload":{"state":{"tick":720,"epoch":5,"round":2,"phase":"countdown","remaining_ms":60000,"phase_remaining_ms":3000,"score":{"t1":1,"t2":0},"characters":[{"team":1,"pos":{"x":0,"z":-6},"aim":{"x":0,"z":1},"held_ball_id":null},{"team":2,"pos":{"x":0,"z":6},"aim":{"x":0,"z":-1},"held_ball_id":null}],"balls":[{"ball_id":"b1","mode":"ground","pos":{"x":-2,"z":-0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0},{"ball_id":"b2","mode":"ground","pos":{"x":2,"z":-0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0},{"ball_id":"b3","mode":"ground","pos":{"x":-2,"z":0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0},{"ball_id":"b4","mode":"ground","pos":{"x":2,"z":0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0}],"assignments":[{"member_id":"p1","team":1,"role":"legs"},{"member_id":"p2","team":1,"role":"arms"},{"member_id":"p3","team":2,"role":"legs"},{"member_id":"p4","team":2,"role":"arms"}],"assignment_version":2,"result":null,"winner":null}}}
```

```json
{"v":1,"type":"phase.changed","server_ms":15000,"payload":{"state":{"tick":900,"epoch":6,"round":2,"phase":"active","remaining_ms":60000,"phase_remaining_ms":null,"score":{"t1":1,"t2":0},"characters":[{"team":1,"pos":{"x":0,"z":-6},"aim":{"x":0,"z":1},"held_ball_id":null},{"team":2,"pos":{"x":0,"z":6},"aim":{"x":0,"z":-1},"held_ball_id":null}],"balls":[{"ball_id":"b1","mode":"ground","pos":{"x":-2,"z":-0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0},{"ball_id":"b2","mode":"ground","pos":{"x":2,"z":-0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0},{"ball_id":"b3","mode":"ground","pos":{"x":-2,"z":0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0},{"ball_id":"b4","mode":"ground","pos":{"x":2,"z":0.6},"velocity":{"x":0,"z":0},"owner_team":null,"shooter_team":null,"respawn_in_ms":0}],"assignments":[{"member_id":"p1","team":1,"role":"legs"},{"member_id":"p2","team":1,"role":"arms"},{"member_id":"p3","team":2,"role":"legs"},{"member_id":"p4","team":2,"role":"arms"}],"assignment_version":2,"result":null,"winner":null}}}
```

17. Disconnection example is a complete room update:

```json
{"v":1,"type":"room.updated","server_ms":13000,"payload":{"room":{"room_id":"r1","room_code":"ABC234","host_id":"s1","revision":12,"members":[{"member_id":"s1","name":"Main screen","device":"screen","connected":true,"ready":false,"permission":"unknown","calibrated":false,"camera_team":null},{"member_id":"p1","name":"Richard","device":"phone","connected":false,"ready":false,"permission":"granted","calibrated":false,"camera_team":null},{"member_id":"p2","name":"Ryan","device":"phone","connected":true,"ready":false,"permission":"granted","calibrated":false,"camera_team":null},{"member_id":"p3","name":"Morteza","device":"phone","connected":true,"ready":false,"permission":"granted","calibrated":false,"camera_team":null},{"member_id":"p4","name":"Tysen","device":"phone","connected":true,"ready":false,"permission":"granted","calibrated":false,"camera_team":null}],"assignments":[{"member_id":"p1","team":1,"role":"legs"},{"member_id":"p2","team":1,"role":"arms"},{"member_id":"p3","team":2,"role":"legs"},{"member_id":"p4","team":2,"role":"arms"}],"assignment_version":2,"phase":"lobby"}}}
```

Other examples: host start `{"v":1,"type":"match.start","payload":{}}`; cancel `{"v":1,"type":"input.arms","payload":{"seq":4,"epoch":2,"aim":{"x":0,"z":1},"action":"cancel","strength":null}}`; rejection `{"v":1,"type":"error","server_ms":5100,"payload":{"code":"NO_THROW_ZONE","message":"Move back before throwing","ref_seq":3}}`.

Error codes are BAD_MESSAGE, UNAUTHORIZED, FORBIDDEN, ROOM_NOT_FOUND, ROOM_FULL, INVALID_PHASE, NOT_READY, STALE_ASSIGNMENT, STALE_EPOCH, OLD_SEQ, WRONG_ROLE, INVALID_INPUT, NO_THROW_ZONE, RATE_LIMIT, SERVER_BUSY. REST may use applicable codes; malformed REST 422 must be normalized to RestError rather than FastAPI's default detail envelope. Expected gameplay rejection keeps socket open; repeated protocol abuse closes it. Secrets and raw sensor values never appear in logs.
