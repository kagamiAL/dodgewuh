// Interfaces from plans/03-api-contracts.md that other owners will publish.
// Copied verbatim so PhoneShell and the session store can be typed today.
// Replace each section with a re-export once its owner's file lands:
//   messages/Transport -> '@/generated/protocol' and '@/net/transport'   (Alan)
//   SensorService      -> '@/sensors/sensorService'                       (Tysen)
// Do not add or rename anything here: 03 is the authority.

import type { Assignment, ID, Phase, State, Vec2 } from '@/game/state'

export type { Assignment, ID, Phase, State, Team, Vec2 } from '@/game/state'
export type Device = 'screen' | 'phone'
export type Permission = 'unknown' | 'granted' | 'denied' | 'unsupported'

// ---- Wire messages (Alan) -------------------------------------------------

export interface Registration { room_id: ID; room_code: string; member_id: ID; token: string; ws_path: string }
export interface Member {
  member_id: ID; name: string; device: Device; connected: boolean
  ready: boolean; permission: Permission; calibrated: boolean
}
export interface Room {
  room_id: ID; room_code: string; host_id: ID; revision: number
  members: Member[]; assignments: Assignment[]; assignment_version: number; phase: Phase
}
export interface Hello { token: string }
export interface Ping { nonce: number }
export interface Ready { epoch: number; assignment_version: number; ready: boolean; permission: Permission; calibrated: boolean }
export type Empty = Record<string, never>
export interface Legs { seq: number; epoch: number; move: Vec2 }
export interface Arms { seq: number; epoch: number; aim: Vec2; action: 'aim' | 'press' | 'release' | 'cancel'; strength: number | null }
export interface Welcome { member_id: ID; room: Room; state: State }
export interface RoomUpdate { room: Room }
export interface Snapshot { state: State }
export interface PhaseChange { state: State }
export interface RolesChanged { assignments: Assignment[]; assignment_version: number; epoch: number }
export interface ErrorPayload { code: string; message: string; ref_seq: number | null }
export interface Closed { reason: 'host_left' | 'expired' | 'server_shutdown' }
export interface ClientPayloads {
  'session.hello': Hello; 'session.ping': Ping; 'controller.ready': Ready
  'match.start': Empty; 'match.reset': Empty; 'match.rematch': Empty
  'input.legs': Legs; 'input.arms': Arms
}
export interface ServerPayloads {
  'session.welcome': Welcome; 'session.pong': Ping; 'room.updated': RoomUpdate
  'state.snapshot': Snapshot; 'phase.changed': PhaseChange; 'roles.changed': RolesChanged
  'error': ErrorPayload; 'room.closed': Closed
}
export type ClientMessage = { [K in keyof ClientPayloads]: { v: 1; type: K; payload: ClientPayloads[K] } }[keyof ClientPayloads]
export type ServerMessage = { [K in keyof ServerPayloads]: { v: 1; type: K; server_ms: number; payload: ServerPayloads[K] } }[keyof ServerPayloads]

export type TransportStatus = 'connecting' | 'connected' | 'reconnecting' | 'closed'
export interface Transport {
  connect(registration: Registration): Promise<void>
  send(message: ClientMessage): void
  subscribe(handler: (message: ServerMessage) => void): () => void
  subscribeStatus(handler: (status: TransportStatus) => void): () => void
  nextInputSeq(): number
  close(): void
}

// ---- Sensors (Tysen) ------------------------------------------------------

export interface SensorSample {
  time_ms: number
  orientation_ms: number | null
  motion_ms: number | null
  beta_deg: number | null
  gamma_deg: number | null
  accel: { x: number; y: number; z: number } | null
  rotation_rate: { alpha: number; beta: number; gamma: number } | null
}
export interface SensorService {
  requestPermissionFromGesture(): Promise<Permission>
  subscribe(handler: (sample: SensorSample) => void): () => void
  stop(): void
}
