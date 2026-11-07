// Single import point for interfaces published by other owners (plans/03-api-contracts.md).
// All three have landed, so this only re-exports them:
//   messages/Transport -> '@/generated/protocol' and '@/net/transport'   (Alan)
//   SensorService      -> '@/sensors/sensorService'                       (Tysen)
// Do not add or rename anything here: 03 is the authority.

export type {
  Arms, Assignment, CameraClaim, Closed, ClientMessage, ClientPayloads, Device, Empty, ErrorPayload, Hello, ID,
  Legs, Member, Permission, Phase, PhaseChange, Ping, Ready, Registration, RolesChanged, Room,
  RoomUpdate, ServerMessage, ServerPayloads, Snapshot, State, Team, Vec2, Welcome,
} from '@/generated/protocol'
export type { Transport, ConnectionStatus as TransportStatus } from '@/net/transport'
export type { SensorSample, SensorService } from '@/sensors/sensorService'
