// Protocol v1; mirrors plans/03-api-contracts.md.
export type ID = string;
export type Team = 1 | 2;
export type Role = 'arms' | 'legs';
export type Device = 'screen' | 'phone' | 'spectator';
export type Phase = 'lobby' | 'countdown' | 'active' | 'round_end' | 'role_switch' | 'match_end';
export type Permission = 'unknown' | 'granted' | 'denied' | 'unsupported';
export type Vec2 = { x: number; z: number };
export interface CreateRoom { name: string }
export interface JoinRoom { name: string; device: Device }
export interface Registration { room_id: ID; room_code: string; member_id: ID; token: string; ws_path: string }
export interface Health { status: 'ok'; build: string; rooms: number }
export interface RestError { code: string; message: string }
export interface Assignment { member_id: ID; team: Team; role: Role }
export interface Member { member_id: ID; name: string; device: Device; connected: boolean;
  ready: boolean; permission: Permission; calibrated: boolean;
  /** Screens only: the team whose Legs this screen's camera drives, else null. */
  camera_team: Team | null }
export interface Room { room_id: ID; room_code: string; host_id: ID; revision: number;
  members: Member[]; assignments: Assignment[]; assignment_version: number; phase: Phase }
export interface Character { team: Team; pos: Vec2; aim: Vec2; held_ball_id: ID | null;
  /** Cosmetic throwing-arm angle in degrees (90 up, >90 back, 0 toward the opponent); animation only. */
  arm_pitch?: number | null }
export interface Ball { ball_id: ID; mode: 'ground' | 'held' | 'flying' | 'respawning';
  pos: Vec2; velocity: Vec2; owner_team: Team | null; shooter_team: Team | null;
  respawn_in_ms: number; height: number }
export interface Result { reason: 'hit' | 'timeout' | 'simultaneous'; winner: Team | null;
  hit_ball_id: ID | null; victim_team: Team | null }
/** A camera dodge in progress (the room runs in slow motion): `team` is the victim of `ball_id`. */
export interface Dodge { ball_id: ID; team: Team; outcome: 'pending' | 'dodged' | 'hit' }
export interface State { tick: number; epoch: number; round: number; phase: Phase;
  remaining_ms: number; phase_remaining_ms: number | null; score: { t1: number; t2: number };
  characters: Character[]; balls: Ball[]; assignments: Assignment[]; assignment_version: number;
  result: Result | null; winner: Team | null;
  /** Non-null only while a camera dodge runs. */
  dodge?: Dodge | null }
export interface Hello { token: string }
export interface Ping { nonce: number }
export interface Ready { epoch: number; assignment_version: number; ready: boolean; permission: Permission; calibrated: boolean }
export interface Empty {}
export interface CameraClaim { team: Team | null }
/** The victim's camera screen: did the Legs player get out of the overlaid ball? */
export interface DodgeResult { epoch: number; ball_id: ID; dodged: boolean }
export interface Legs { seq: number; epoch: number; move: Vec2 }
export interface Arms { seq: number; epoch: number; aim: Vec2;
  action: 'aim' | 'press' | 'release' | 'cancel'; strength: number | null;
  /** Optional, cosmetic: throwing-arm angle in degrees for the screen's throw animation. */
  arm_pitch?: number | null }
export interface Welcome { member_id: ID; room: Room; state: State }
export interface RoomUpdate { room: Room }
export interface Snapshot { state: State }
export interface PhaseChange { state: State }
export interface RolesChanged { assignments: Assignment[]; assignment_version: number; epoch: number }
export interface ErrorPayload { code: string; message: string; ref_seq: number | null }
export interface Closed { reason: 'host_left' | 'expired' | 'server_shutdown' }
export interface ClientPayloads {
  'session.hello': Hello; 'session.ping': Ping; 'controller.ready': Ready;
  'match.start': Empty; 'match.reset': Empty; 'match.rematch': Empty;
  'input.legs': Legs; 'input.arms': Arms; 'camera.claim': CameraClaim; 'team.choose': CameraClaim;
  'dodge.result': DodgeResult;
}
export interface ServerPayloads {
  'session.welcome': Welcome; 'session.pong': Ping; 'room.updated': RoomUpdate;
  'state.snapshot': Snapshot; 'phase.changed': PhaseChange; 'roles.changed': RolesChanged;
  'error': ErrorPayload; 'room.closed': Closed;
}
export type ClientMessage = { [K in keyof ClientPayloads]: {v: 1; type: K; payload: ClientPayloads[K]} }[keyof ClientPayloads];
export type ServerMessage = { [K in keyof ServerPayloads]: {v: 1; type: K; server_ms: number; payload: ServerPayloads[K]} }[keyof ServerPayloads];
